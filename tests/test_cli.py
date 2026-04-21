"""Tests for crossreview.cli — 1C.1 pack CLI."""

from __future__ import annotations

import json
from unittest.mock import patch

from crossreview.cli import main
from crossreview.schema import FileMeta


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
    """crossreview verify CLI stub."""

    def test_verify_not_implemented(self, capsys):
        rc = main(["verify"])
        assert rc == 1
        assert "not yet implemented" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# No subcommand
# ---------------------------------------------------------------------------

class TestNoCommand:
    def test_no_args_prints_help(self, capsys):
        rc = main([])
        assert rc == 1
