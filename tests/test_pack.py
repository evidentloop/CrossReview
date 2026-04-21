"""Tests for crossreview.pack — 1B.1 pack assembly."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crossreview.pack import (
    GitDiffError,
    assemble_pack,
    changed_files_from_git,
    compute_pack_completeness,
    detect_language,
    diff_from_git,
    extract_changed_files,
    pack_to_dict,
    pack_to_json,
    read_context_files,
    read_task_file,
)
from crossreview.schema import (
    ArtifactType,
    ContextFile,
    Evidence,
    EvidenceStatus,
    FileMeta,
    PackBudget,
    ReviewPack,
    SCHEMA_VERSION,
    compute_fingerprint,
    validate_review_pack,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SIMPLE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc1234..def5678 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@
 def login(user):
     token = create_token(user)
+    log_login(user)
     return token
"""

MULTI_FILE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1,2 @@
 def login(): pass
+def logout(): pass
diff --git a/tests/test_auth.py b/tests/test_auth.py
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,3 @@
+def test_login():
+    assert login()
+    assert logout()
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Auth
+Updated docs
"""

DELETE_DIFF = """\
diff --git a/old_module.py b/old_module.py
--- a/old_module.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def legacy():
-    pass
-
"""

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
"""


# ===== Language Detection =====

class TestDetectLanguage:
    """Language detection from file extension."""

    @pytest.mark.parametrize("path,expected", [
        ("main.py", "python"),
        ("app.js", "javascript"),
        ("index.ts", "typescript"),
        ("component.tsx", "typescript"),
        ("main.go", "go"),
        ("lib.rs", "rust"),
        ("App.java", "java"),
        ("script.sh", "shell"),
        ("config.yaml", "yaml"),
        ("settings.yml", "yaml"),
        ("data.json", "json"),
        ("pyproject.toml", "toml"),
        ("README.md", "markdown"),
        ("page.html", "html"),
        ("style.css", "css"),
        ("query.sql", "sql"),
        ("build.kt", "kotlin"),
        ("server.rb", "ruby"),
        ("main.c", "c"),
        ("util.cpp", "cpp"),
        ("header.h", "c"),
        ("header.hpp", "cpp"),
        ("App.swift", "swift"),
        ("Program.cs", "csharp"),
        ("app.vue", "vue"),
        ("App.svelte", "svelte"),
        ("mix.exs", "elixir"),
        ("init.lua", "lua"),
        ("index.php", "php"),
        ("stub.pyi", "python"),
        ("module.mjs", "javascript"),
    ])
    def test_known_extensions(self, path: str, expected: str):
        assert detect_language(path) == expected

    def test_unknown_extension(self):
        assert detect_language("Makefile") is None
        assert detect_language("data.xyz") is None

    def test_nested_path(self):
        assert detect_language("src/deep/nested/module.py") == "python"


# ===== Extract Changed Files =====

class TestExtractChangedFiles:
    """Parse unified diff to extract FileMeta list."""

    def test_single_file(self):
        files = extract_changed_files(SIMPLE_DIFF)
        assert len(files) == 1
        assert files[0].path == "src/auth.py"
        assert files[0].language == "python"

    def test_multi_file(self):
        files = extract_changed_files(MULTI_FILE_DIFF)
        assert len(files) == 3
        paths = [f.path for f in files]
        assert "src/auth.py" in paths
        assert "tests/test_auth.py" in paths
        assert "README.md" in paths

    def test_new_file(self):
        files = extract_changed_files(MULTI_FILE_DIFF)
        test_file = next(f for f in files if f.path == "tests/test_auth.py")
        assert test_file.language == "python"

    def test_deleted_file(self):
        files = extract_changed_files(DELETE_DIFF)
        assert len(files) == 1
        assert files[0].path == "old_module.py"

    def test_rename(self):
        files = extract_changed_files(RENAME_DIFF)
        assert len(files) == 1
        assert files[0].path == "new_name.py"

    def test_empty_diff(self):
        assert extract_changed_files("") == []

    def test_dedup(self):
        """Same file appearing twice in diff should be deduped."""
        double = SIMPLE_DIFF + SIMPLE_DIFF
        files = extract_changed_files(double)
        assert len(files) == 1

    def test_language_for_various_files(self):
        files = extract_changed_files(MULTI_FILE_DIFF)
        lang_map = {f.path: f.language for f in files}
        assert lang_map["src/auth.py"] == "python"
        assert lang_map["tests/test_auth.py"] == "python"
        assert lang_map["README.md"] == "markdown"


# ===== Pack Completeness =====

class TestPackCompleteness:
    """v0-scope.md §10.2 pack_completeness scoring."""

    def test_minimal_pack(self):
        """Only diff + changed_files → 0.40."""
        pack = ReviewPack(
            diff="some diff",
            changed_files=[FileMeta(path="a.py")],
        )
        assert compute_pack_completeness(pack) == 0.40

    def test_with_intent(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            intent="fix auth",
        )
        assert compute_pack_completeness(pack) == 0.65

    def test_with_task_file(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            task_file="content of task",
        )
        assert compute_pack_completeness(pack) == 0.65

    def test_intent_and_task_no_double_count(self):
        """intent + task_file together still only +0.25."""
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            intent="fix",
            task_file="details",
        )
        assert compute_pack_completeness(pack) == 0.65

    def test_full_pack(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            intent="fix auth",
            focus=["auth"],
            context_files=[ContextFile(path="p.md", content="plan")],
            evidence=[Evidence(source="pytest", status=EvidenceStatus.PASS, summary="ok")],
        )
        assert compute_pack_completeness(pack) == 1.0

    def test_empty_pack(self):
        pack = ReviewPack()
        assert compute_pack_completeness(pack) == 0.0

    def test_focus_only_adds_0_10(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            focus=["module_x"],
        )
        assert compute_pack_completeness(pack) == 0.50

    def test_empty_lists_dont_count(self):
        """Empty list for focus should not add score."""
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            focus=[],
        )
        assert compute_pack_completeness(pack) == 0.40


# ===== Serialization =====

class TestSerialization:
    """pack_to_dict / pack_to_json round-trip correctness."""

    def test_minimal_dict(self):
        pack = ReviewPack(
            diff="diff content",
            changed_files=[FileMeta(path="a.py", language="python")],
            artifact_fingerprint="abc",
            pack_fingerprint="def",
        )
        d = pack_to_dict(pack)
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["artifact_type"] == "code_diff"
        assert d["diff"] == "diff content"
        assert d["changed_files"] == [{"path": "a.py", "language": "python"}]
        assert d["artifact_fingerprint"] == "abc"
        assert d["pack_fingerprint"] == "def"

    def test_enums_serialized_as_values(self):
        d = pack_to_dict(ReviewPack(
            diff="d",
            changed_files=[FileMeta(path="x")],
            artifact_fingerprint="a",
            pack_fingerprint="b",
        ))
        assert isinstance(d["artifact_type"], str)
        assert d["artifact_type"] == "code_diff"

    def test_none_fields_present(self):
        d = pack_to_dict(ReviewPack())
        assert d["intent"] is None
        assert d["task_file"] is None
        assert d["focus"] is None

    def test_json_roundtrip(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            artifact_fingerprint="abc",
            pack_fingerprint="def",
            intent="fix bug",
            focus=["auth"],
        )
        json_str = pack_to_json(pack)
        parsed = json.loads(json_str)
        assert parsed["intent"] == "fix bug"
        assert parsed["focus"] == ["auth"]
        assert parsed["artifact_type"] == "code_diff"

    def test_exclude_pack_fp(self):
        pack = ReviewPack(
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
            artifact_fingerprint="abc",
            pack_fingerprint="real_fp",
        )
        json_str = pack_to_json(pack, exclude_pack_fp=True)
        parsed = json.loads(json_str)
        assert parsed["pack_fingerprint"] == ""

    def test_context_files_serialized(self):
        pack = ReviewPack(
            diff="d",
            changed_files=[FileMeta(path="x")],
            artifact_fingerprint="a",
            pack_fingerprint="b",
            context_files=[ContextFile(path="p.md", content="plan", role="plan")],
        )
        d = pack_to_dict(pack)
        assert d["context_files"] == [
            {"path": "p.md", "content": "plan", "role": "plan"}
        ]

    def test_evidence_serialized(self):
        pack = ReviewPack(
            diff="d",
            changed_files=[FileMeta(path="x")],
            artifact_fingerprint="a",
            pack_fingerprint="b",
            evidence=[Evidence(
                source="pytest",
                status=EvidenceStatus.PASS,
                summary="all ok",
                command="pytest -q",
            )],
        )
        d = pack_to_dict(pack)
        ev = d["evidence"][0]
        assert ev["source"] == "pytest"
        assert ev["status"] == "pass"
        assert ev["command"] == "pytest -q"

    def test_budget_serialized(self):
        pack = ReviewPack(
            diff="d",
            changed_files=[FileMeta(path="x")],
            artifact_fingerprint="a",
            pack_fingerprint="b",
            budget=PackBudget(max_files=10, max_chars_total=50000),
        )
        d = pack_to_dict(pack)
        assert d["budget"]["max_files"] == 10
        assert d["budget"]["max_chars_total"] == 50000
        assert d["budget"]["timeout_sec"] is None


# ===== Git Changed Files =====

class TestChangedFilesFromGit:
    """changed_files_from_git — NUL-delimited subprocess integration."""

    @patch("crossreview.pack.subprocess.run")
    def test_basic(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="src/auth.py\0tests/test_auth.py\0")
        files = changed_files_from_git("HEAD~1")
        assert len(files) == 2
        assert files[0].path == "src/auth.py"
        assert files[0].language == "python"
        assert files[1].path == "tests/test_auth.py"

    @patch("crossreview.pack.subprocess.run")
    def test_special_chars_in_path(self, mock_run: MagicMock):
        """NUL-delimited output handles paths with tabs/spaces correctly."""
        mock_run.return_value = MagicMock(stdout="file\twith\ttabs.py\0space file.js\0")
        files = changed_files_from_git("HEAD~1")
        assert len(files) == 2
        assert files[0].path == "file\twith\ttabs.py"
        assert files[1].path == "space file.js"

    @patch("crossreview.pack.subprocess.run")
    def test_path_with_b_slash(self, mock_run: MagicMock):
        """Paths containing ' b/' are handled correctly (no regex split issue)."""
        mock_run.return_value = MagicMock(stdout="docs/file b/section.md\0")
        files = changed_files_from_git("HEAD~1")
        assert len(files) == 1
        assert files[0].path == "docs/file b/section.md"

    @patch("crossreview.pack.subprocess.run")
    def test_empty_output(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="")
        files = changed_files_from_git("HEAD~1")
        assert files == []

    @patch("crossreview.pack.subprocess.run")
    def test_command_structure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="")
        changed_files_from_git("HEAD~1")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "--no-pager", "diff", "--name-only", "-z", "HEAD~1", "HEAD"]

    @patch("crossreview.pack.subprocess.run")
    def test_range_ref(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="a.py\0")
        changed_files_from_git("abc..def")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "--no-pager", "diff", "--name-only", "-z", "abc..def"]

    @patch("crossreview.pack.subprocess.run")
    def test_git_failure_raises(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr="fatal: bad ref"
        )
        with pytest.raises(GitDiffError, match="git diff --name-only failed"):
            changed_files_from_git("nonexistent")

    @patch("crossreview.pack.subprocess.run")
    def test_dedup(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="a.py\0a.py\0")
        files = changed_files_from_git("HEAD~1")
        assert len(files) == 1


# ===== Git Diff =====

class TestDiffFromGit:
    """diff_from_git — subprocess integration."""

    @patch("crossreview.pack.subprocess.run")
    def test_simple_ref(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="diff output")
        result = diff_from_git("HEAD~1")
        assert result == "diff output"
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "--no-pager", "diff", "HEAD~1", "HEAD"]

    @patch("crossreview.pack.subprocess.run")
    def test_range_ref(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="range diff")
        result = diff_from_git("abc..def")
        assert result == "range diff"
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "--no-pager", "diff", "abc..def"]

    @patch("crossreview.pack.subprocess.run")
    def test_repo_root_passed(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(stdout="")
        diff_from_git("HEAD~1", repo_root=Path("/tmp/repo"))
        assert mock_run.call_args[1]["cwd"] == Path("/tmp/repo")

    @patch("crossreview.pack.subprocess.run")
    def test_git_failure_raises(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr="fatal: bad ref"
        )
        with pytest.raises(GitDiffError, match="git diff failed"):
            diff_from_git("nonexistent")


# ===== Assemble Pack =====

class TestAssemblePack:
    """End-to-end pack assembly."""

    def test_minimal_assembly(self):
        pack = assemble_pack(SIMPLE_DIFF)
        assert pack.schema_version == SCHEMA_VERSION
        assert pack.artifact_type == ArtifactType.CODE_DIFF
        assert pack.diff == SIMPLE_DIFF
        assert len(pack.changed_files) == 1
        assert pack.changed_files[0].path == "src/auth.py"
        assert pack.artifact_fingerprint
        assert pack.pack_fingerprint
        assert pack.artifact_fingerprint != pack.pack_fingerprint

    def test_with_intent(self):
        pack = assemble_pack(SIMPLE_DIFF, intent="fix auth")
        assert pack.intent == "fix auth"

    def test_with_focus(self):
        pack = assemble_pack(SIMPLE_DIFF, focus=["auth", "security"])
        assert pack.focus == ["auth", "security"]

    def test_with_task_file(self):
        pack = assemble_pack(SIMPLE_DIFF, task_file="task description content")
        assert pack.task_file == "task description content"

    def test_with_context_files(self):
        ctx = [ContextFile(path="plan.md", content="the plan")]
        pack = assemble_pack(SIMPLE_DIFF, context_files=ctx)
        assert pack.context_files is not None
        assert len(pack.context_files) == 1

    def test_custom_changed_files(self):
        """Caller can override changed_files (skip diff parsing)."""
        custom = [FileMeta(path="custom.py", language="python")]
        pack = assemble_pack(SIMPLE_DIFF, changed_files=custom)
        assert len(pack.changed_files) == 1
        assert pack.changed_files[0].path == "custom.py"

    def test_artifact_fingerprint_is_diff_hash(self):
        pack = assemble_pack(SIMPLE_DIFF)
        expected = compute_fingerprint(SIMPLE_DIFF)
        assert pack.artifact_fingerprint == expected

    def test_pack_fingerprint_stable(self):
        """Same inputs → same pack_fingerprint."""
        p1 = assemble_pack(SIMPLE_DIFF, intent="fix")
        p2 = assemble_pack(SIMPLE_DIFF, intent="fix")
        assert p1.pack_fingerprint == p2.pack_fingerprint

    def test_pack_fingerprint_changes_with_intent(self):
        p1 = assemble_pack(SIMPLE_DIFF, intent="fix auth")
        p2 = assemble_pack(SIMPLE_DIFF, intent="add logging")
        assert p1.pack_fingerprint != p2.pack_fingerprint

    def test_empty_diff_raises(self):
        with pytest.raises(ValueError, match="diff_required"):
            assemble_pack("")

    def test_validates_on_assembly(self):
        """assemble_pack runs validate_review_pack internally."""
        pack = assemble_pack(SIMPLE_DIFF)
        # If we got here, validation passed
        assert validate_review_pack(pack) == []

    def test_multi_file_assembly(self):
        pack = assemble_pack(MULTI_FILE_DIFF)
        assert len(pack.changed_files) == 3

    def test_budget_passthrough(self):
        budget = PackBudget(max_files=5, timeout_sec=30)
        pack = assemble_pack(SIMPLE_DIFF, budget=budget)
        assert pack.budget.max_files == 5
        assert pack.budget.timeout_sec == 30

    def test_default_budget(self):
        pack = assemble_pack(SIMPLE_DIFF)
        assert pack.budget.max_files is None


# ===== File I/O =====

class TestFileIO:
    """read_task_file / read_context_files."""

    def test_read_task_file(self, tmp_path: Path):
        f = tmp_path / "task.md"
        f.write_text("# Task\nDo the thing.", encoding="utf-8")
        assert read_task_file(str(f)) == "# Task\nDo the thing."

    def test_read_task_file_missing(self):
        with pytest.raises(FileNotFoundError):
            read_task_file("/nonexistent/task.md")

    def test_read_context_files(self, tmp_path: Path):
        f1 = tmp_path / "plan.md"
        f2 = tmp_path / "design.md"
        f1.write_text("plan", encoding="utf-8")
        f2.write_text("design", encoding="utf-8")
        result = read_context_files([str(f1), str(f2)])
        assert len(result) == 2
        assert result[0].path == str(f1)
        assert result[0].content == "plan"
        assert result[1].content == "design"

    def test_read_context_file_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_context_files([str(tmp_path / "nonexistent.md")])
