"""Tests for crossreview.cli — 1C.1 pack CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from crossreview.cli import main
from crossreview.pack import assemble_pack, pack_to_json
from crossreview.schema import (
    BudgetStatus,
    Confidence,
    FileMeta,
    Finding,
    LocalizabilityDistribution,
    Locatability,
    QualityMetrics,
    ReviewerFailureReason,
    Severity,
)


# ---------------------------------------------------------------------------
# Pack subcommand
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/hello.py b/hello.py
--- a/hello.py
+++ b/hello.py
@@ -1 +1,2 @@
 print("hello")
+print("world")
"""

SAMPLE_FILES = [FileMeta(path="hello.py", language="python")]


def _patch_git():
    """Patch both diff_from_git and changed_files_from_git for CLI tests."""
    return (
        patch("crossreview.cli.diff_from_git", return_value=SAMPLE_DIFF),
        patch("crossreview.cli.changed_files_from_git", return_value=SAMPLE_FILES),
    )


class TestPackCLI:
    """crossreview pack CLI integration."""

    def test_basic_pack(self, capsys):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1"])
        assert rc == 0
        out = capsys.readouterr()
        parsed = json.loads(out.out)
        assert parsed["schema_version"] == "0.1-alpha"
        assert parsed["artifact_type"] == "code_diff"
        assert parsed["diff"] == SAMPLE_DIFF
        assert len(parsed["changed_files"]) == 1
        assert parsed["changed_files"][0]["path"] == "hello.py"
        assert parsed["artifact_fingerprint"]
        assert parsed["pack_fingerprint"]
        assert "completeness=" in out.err

    def test_with_intent(self, capsys):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--intent", "fix greeting"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["intent"] == "fix greeting"

    def test_with_focus(self, capsys):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--focus", "auth", "--focus", "db"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["focus"] == ["auth", "db"]

    def test_with_task_file(self, capsys, tmp_path):
        task = tmp_path / "task.md"
        task.write_text("implement feature X", encoding="utf-8")
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--task", str(task)])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["task_file"] == "implement feature X"

    def test_with_context(self, capsys, tmp_path):
        ctx = tmp_path / "plan.md"
        ctx.write_text("the plan", encoding="utf-8")
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--context", str(ctx)])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["context_files"] is not None
        assert len(parsed["context_files"]) == 1
        assert parsed["context_files"][0]["content"] == "the plan"

    def test_empty_diff_error(self, capsys):
        with patch("crossreview.cli.diff_from_git", return_value=""):
            rc = main(["pack", "--diff", "HEAD~1"])
        assert rc == 1
        assert "empty output" in capsys.readouterr().err

    def test_git_error(self, capsys):
        from crossreview.pack import GitDiffError
        with patch("crossreview.cli.diff_from_git", side_effect=GitDiffError("fatal: bad ref")):
            rc = main(["pack", "--diff", "bad_ref"])
        assert rc == 1
        assert "fatal: bad ref" in capsys.readouterr().err

    def test_missing_task_file_error(self, capsys):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--task", "/nonexistent/task.md"])
        assert rc == 1
        assert "cannot read task file" in capsys.readouterr().err

    def test_missing_context_file_error(self, capsys):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--context", "/nonexistent/ctx.md"])
        assert rc == 1
        assert "cannot read context file" in capsys.readouterr().err

    def test_task_file_is_directory_error(self, capsys, tmp_path):
        with _patch_git()[0], _patch_git()[1]:
            rc = main(["pack", "--diff", "HEAD~1", "--task", str(tmp_path)])
        assert rc == 1
        assert "cannot read task file" in capsys.readouterr().err

    def test_changed_files_git_error(self, capsys):
        """If changed_files_from_git fails, CLI reports error."""
        from crossreview.pack import GitDiffError
        with (
            patch("crossreview.cli.diff_from_git", return_value=SAMPLE_DIFF),
            patch("crossreview.cli.changed_files_from_git", side_effect=GitDiffError("fail")),
        ):
            rc = main(["pack", "--diff", "HEAD~1"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Verify subcommand (stub)
# ---------------------------------------------------------------------------

class TestVerifyCLI:
    """crossreview verify CLI."""

    def _write_pack(self, tmp_path: Path, **kwargs) -> Path:
        pack = assemble_pack(
            SAMPLE_DIFF,
            changed_files=SAMPLE_FILES,
            **kwargs,
        )
        path = tmp_path / "pack.json"
        path.write_text(pack_to_json(pack), encoding="utf-8")
        return path

    def test_verify_success(self, capsys, tmp_path):
        pack_path = self._write_pack(tmp_path, intent="fix greeting")
        with (
            patch("crossreview.cli.resolve_reviewer_config") as resolve_cfg,
            patch("crossreview.cli.resolve_reviewer_backend") as resolve_backend,
        ):
            resolve_cfg.return_value = type(
                "Cfg",
                (),
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "api_key_env": "ANTHROPIC_API_KEY",
                },
            )()
            backend = resolve_backend.return_value
            backend.review.return_value = type(
                "Resp",
                (),
                {
                    "raw_analysis": """## Section 1: Findings

**f-001**
- **Where**: `hello.py`, line 2
- **What**: The new print changes behavior.
- **Why**: The diff now prints an extra line.
- **Severity estimate**: LOW
- **Category**: spec_mismatch
""",
                    "model": "claude-sonnet-4-20250514",
                    "latency_sec": 1.2,
                    "input_tokens": 100,
                    "output_tokens": 80,
                },
            )()
            rc = main(["verify", "--pack", str(pack_path)])

        assert rc == 0
        out = capsys.readouterr()
        parsed = json.loads(out.out)
        assert parsed["review_status"] == "complete"
        assert parsed["reviewer"]["model"] == "claude-sonnet-4-20250514"
        assert len(parsed["raw_findings"]) == 1
        assert parsed["findings"][0]["id"] == "f-001"
        assert "crossreview verify: review_status=complete" in out.err

    def test_verify_preserves_raw_findings_before_noise_cap(self, capsys, tmp_path):
        pack_path = self._write_pack(tmp_path, intent="fix greeting")
        with (
            patch("crossreview.cli.resolve_reviewer_config") as resolve_cfg,
            patch("crossreview.cli.resolve_reviewer_backend") as resolve_backend,
            patch("crossreview.cli.normalize_review_output") as normalize_output,
        ):
            resolve_cfg.return_value = type(
                "Cfg",
                (),
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "api_key_env": "ANTHROPIC_API_KEY",
                },
            )()
            backend = resolve_backend.return_value
            backend.review.return_value = type(
                "Resp",
                (),
                {
                    "raw_analysis": "raw",
                    "model": "claude-sonnet-4-20250514",
                    "latency_sec": 1.2,
                    "input_tokens": 100,
                    "output_tokens": 80,
                },
            )()
            normalize_output.return_value = type(
                "Norm",
                (),
                {
                    "raw_findings": [
                        Finding(
                            id="f-001",
                            severity=Severity.MEDIUM,
                            summary="s1",
                            detail="d1",
                            category="logic_error",
                            locatability=Locatability.EXACT,
                            confidence=Confidence.PLAUSIBLE,
                            evidence_related_file=False,
                            actionable=True,
                            file="hello.py",
                            line=2,
                        ),
                        Finding(
                            id="f-002",
                            severity=Severity.LOW,
                            summary="s2",
                            detail="d2",
                            category="style",
                            locatability=Locatability.FILE_ONLY,
                            confidence=Confidence.SPECULATIVE,
                            evidence_related_file=False,
                            actionable=False,
                            file="hello.py",
                        ),
                    ],
                    "findings": [
                        Finding(
                            id="f-001",
                            severity=Severity.MEDIUM,
                            summary="s1",
                            detail="d1",
                            category="logic_error",
                            locatability=Locatability.EXACT,
                            confidence=Confidence.PLAUSIBLE,
                            evidence_related_file=False,
                            actionable=True,
                            file="hello.py",
                            line=2,
                        )
                    ],
                    "quality_metrics": QualityMetrics(
                        pack_completeness=0.8,
                        noise_count=1,
                        raw_findings_count=2,
                        emitted_findings_count=1,
                        locatability_distribution=LocalizabilityDistribution(
                            exact_pct=1.0,
                            file_only_pct=0.0,
                            none_pct=0.0,
                        ),
                        speculative_ratio=0.0,
                    ),
                },
            )()

            rc = main(["verify", "--pack", str(pack_path)])

        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["quality_metrics"]["raw_findings_count"] == 2
        assert parsed["quality_metrics"]["emitted_findings_count"] == 1
        assert len(parsed["raw_findings"]) == 2
        assert len(parsed["findings"]) == 1

    def test_verify_invalid_json(self, capsys, tmp_path):
        pack_path = tmp_path / "pack.json"
        pack_path.write_text("{not json", encoding="utf-8")
        rc = main(["verify", "--pack", str(pack_path)])
        assert rc == 1
        assert "not valid JSON" in capsys.readouterr().err

    def test_verify_invalid_pack_fails(self, capsys, tmp_path):
        pack_path = tmp_path / "pack.json"
        pack_path.write_text(json.dumps({"schema_version": "0.1-alpha"}), encoding="utf-8")
        rc = main(["verify", "--pack", str(pack_path)])
        assert rc == 1
        assert "invalid ReviewPack" in capsys.readouterr().err

    def test_verify_budget_rejected_returns_result(self, capsys, tmp_path):
        pack_path = self._write_pack(tmp_path)
        with (
            patch("crossreview.cli.resolve_reviewer_config") as resolve_cfg,
            patch("crossreview.cli.apply_budget_gate") as gate,
        ):
            resolve_cfg.return_value = type(
                "Cfg",
                (),
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "api_key_env": "ANTHROPIC_API_KEY",
                },
            )()
            gate.return_value = type(
                "Gate",
                (),
                {
                    "status": BudgetStatus.REJECTED,
                    "effective_pack": None,
                    "files_reviewed": 0,
                    "files_total": 1,
                    "chars_consumed": 0,
                    "chars_limit": 100,
                    "failure_reason": ReviewerFailureReason.CONTEXT_TOO_LARGE,
                },
            )()
            rc = main(["verify", "--pack", str(pack_path)])

        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["review_status"] == "rejected"
        assert parsed["budget"]["status"] == "rejected"

    def test_verify_reviewer_failure_returns_failed_result(self, capsys, tmp_path):
        pack_path = self._write_pack(tmp_path)
        with (
            patch("crossreview.cli.resolve_reviewer_config") as resolve_cfg,
            patch("crossreview.cli.resolve_reviewer_backend") as resolve_backend,
        ):
            resolve_cfg.return_value = type(
                "Cfg",
                (),
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "api_key_env": "ANTHROPIC_API_KEY",
                },
            )()
            backend = resolve_backend.return_value
            from crossreview.reviewer import ReviewerDependencyError

            backend.review.side_effect = ReviewerDependencyError("missing anthropic")
            rc = main(["verify", "--pack", str(pack_path)])

        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["review_status"] == "failed"
        assert parsed["reviewer"]["failure_reason"] == "model_error"

    def test_verify_config_error(self, capsys, tmp_path):
        pack_path = self._write_pack(tmp_path)
        from crossreview.config import ModelNotConfigured

        with patch("crossreview.cli.resolve_reviewer_config", side_effect=ModelNotConfigured("missing")):
            rc = main(["verify", "--pack", str(pack_path)])

        assert rc == 1
        assert "missing" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# No subcommand
# ---------------------------------------------------------------------------

class TestNoCommand:
    def test_no_args_prints_help(self, capsys):
        rc = main([])
        assert rc == 1
