"""Tests for Prompt Lab runner adapter behavior."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from crossreview.pack import assemble_pack
from crossreview.schema import ReviewResult, ReviewerMeta, SCHEMA_VERSION


SAMPLE_DIFF = """\
diff --git a/hello.py b/hello.py
--- a/hello.py
+++ b/hello.py
@@ -1 +1,2 @@
 print("hello")
+print("world")
"""


def _load_prompt_lab_run():
    module_path = Path(__file__).resolve().parents[1] / "prompt-lab" / "run.py"
    spec = importlib.util.spec_from_file_location("prompt_lab_run", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "pack.json").write_text(
        json.dumps(
            {
                "artifact_type": "code_diff",
                "diff": SAMPLE_DIFF,
                "changed_files": ["hello.py"],
                "intent": "fix greeting",
            }
        ),
        encoding="utf-8",
    )
    return case_dir


def _write_case_with_pack(tmp_path: Path, pack: dict) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
    return case_dir


class TestPromptLabRun:
    def test_load_review_pack_reassembles_legacy_pack_with_fingerprints(self, tmp_path):
        runner = _load_prompt_lab_run()
        pack = runner.load_review_pack(_write_case(tmp_path))

        assert pack.artifact_fingerprint
        assert pack.pack_fingerprint
        assert pack.changed_files[0].path == "hello.py"

    def test_load_review_pack_preserves_legacy_changed_files_order(self, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = _write_case_with_pack(
            tmp_path,
            {
                "artifact_type": "code_diff",
                "diff": SAMPLE_DIFF,
                "changed_files": [
                    {"path": "z_first.py", "language": "python"},
                    "a_second.py",
                ],
            },
        )

        pack = runner.load_review_pack(case_dir)

        assert [item.path for item in pack.changed_files] == ["z_first.py", "a_second.py"]
        assert pack.changed_files[0].language == "python"

    def test_render_only_keeps_prompt_lab_template_seam(self):
        runner = _load_prompt_lab_run()

        assert "CrossReview Reviewer Prompt Template (v0.2)" in runner.load_prompt_lab_template()

    def test_api_only_writes_canonical_review_result_json(self, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = _write_case(tmp_path)
        pack = assemble_pack(SAMPLE_DIFF)
        result = ReviewResult(
            schema_version=SCHEMA_VERSION,
            artifact_fingerprint=pack.artifact_fingerprint,
            pack_fingerprint=pack.pack_fingerprint,
            reviewer=ReviewerMeta(model="claude-sonnet-4-20250514"),
        )

        with (
            patch.object(runner, "resolve_reviewer_config") as resolve_config,
            patch.object(runner, "run_verify_pack", return_value=result),
        ):
            resolve_config.return_value = object()
            rc = runner.run_api_only(case_dir, label="test")

        assert rc == 0
        output = json.loads((case_dir / "run-test.json").read_text(encoding="utf-8"))
        assert output["schema_version"] == "0.1-alpha"
        assert output["reviewer"]["model"] == "claude-sonnet-4-20250514"

    def test_api_only_passes_cli_flags_to_resolve_reviewer_config(self, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = _write_case(tmp_path)
        pack = assemble_pack(SAMPLE_DIFF)
        result = ReviewResult(
            schema_version=SCHEMA_VERSION,
            artifact_fingerprint=pack.artifact_fingerprint,
            pack_fingerprint=pack.pack_fingerprint,
            reviewer=ReviewerMeta(model="claude-opus-4-5-20251101"),
        )

        with (
            patch.object(runner, "resolve_reviewer_config") as resolve_config,
            patch.object(runner, "run_verify_pack", return_value=result),
        ):
            resolve_config.return_value = object()
            runner.run_api_only(
                case_dir,
                label="r4",
                provider="anthropic",
                model="claude-opus-4-5-20251101",
                api_key_env="ANTHROPIC_API_KEY",
            )

        resolve_config.assert_called_once_with(
            cli_provider="anthropic",
            cli_model="claude-opus-4-5-20251101",
            cli_api_key_env="ANTHROPIC_API_KEY",
        )

    def test_main_passes_parser_flags_to_api_only_runner(self, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = _write_case(tmp_path)

        with (
            patch.object(
                runner.sys,
                "argv",
                [
                    "run.py",
                    "--api-only",
                    "--provider",
                    "anthropic",
                    "--model",
                    "claude-opus-4-5-20251101",
                    "--api-key-env",
                    "ANTHROPIC_API_KEY",
                    "--label",
                    "r4",
                    str(case_dir),
                ],
            ),
            patch.object(runner, "run_api_only", return_value=0) as run_api_only,
        ):
            try:
                runner.main()
            except SystemExit as exc:
                assert exc.code == 0

        run_api_only.assert_called_once_with(
            case_dir,
            label="r4",
            provider="anthropic",
            model="claude-opus-4-5-20251101",
            api_key_env="ANTHROPIC_API_KEY",
        )

    def test_main_rejects_unknown_flags(self, capsys, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = _write_case(tmp_path)

        with patch.object(
            runner.sys,
            "argv",
            ["run.py", "--api-only", "--modle", "typo", str(case_dir)],
        ):
            try:
                runner.main()
            except SystemExit as exc:
                assert exc.code == 2

        assert "unrecognized arguments: --modle" in capsys.readouterr().err

    def test_render_only_reports_missing_pack_without_traceback(self, capsys, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = tmp_path / "case"
        case_dir.mkdir()

        with patch.object(runner.sys, "argv", ["run.py", "--render-only", str(case_dir)]):
            try:
                runner.main()
            except SystemExit as exc:
                assert exc.code == 1

        assert "pack.json not found" in capsys.readouterr().err

    def test_api_only_writes_rejected_result_for_unmappable_legacy_pack(self, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = tmp_path / "bad-case"
        case_dir.mkdir()
        (case_dir / "pack.json").write_text(
            json.dumps(
                {
                    "artifact_type": "code_diff",
                    "diff": "not a unified git diff",
                    "changed_files": ["missing.py"],
                }
            ),
            encoding="utf-8",
        )

        rc = runner.run_api_only(
            case_dir,
            label="bad",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env="ANTHROPIC_API_KEY",
        )

        assert rc == 0
        output = json.loads((case_dir / "run-bad.json").read_text(encoding="utf-8"))
        assert output["review_status"] == "rejected"
        assert output["reviewer"]["failure_reason"] == "input_invalid"

    def test_api_only_returns_error_for_invalid_legacy_pack_shape(self, capsys, tmp_path):
        runner = _load_prompt_lab_run()
        case_dir = tmp_path / "bad-case"
        case_dir.mkdir()
        (case_dir / "pack.json").write_text(
            json.dumps(
                {
                    "artifact_type": "code_diff",
                    "diff": SAMPLE_DIFF,
                    "changed_files": [],
                }
            ),
            encoding="utf-8",
        )

        rc = runner.run_api_only(
            case_dir,
            label="bad",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env="ANTHROPIC_API_KEY",
        )

        assert rc == 1
        assert "changed_files" in capsys.readouterr().err
        assert not (case_dir / "run-bad.json").exists()
