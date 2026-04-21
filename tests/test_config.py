"""Tests for crossreview.config — covers 1A.4.

Validates:
  - Config resolution priority order (CLI > project yaml > user yaml > env)
  - ModelNotConfigured error when no source provides model
  - Partial config merging across layers
  - ReviewerConfig has all 3 fields (provider, model, api_key_env)
"""

from pathlib import Path

import pytest

from crossreview.config import (
    ConfigError,
    ModelNotConfigured,
    resolve_reviewer_config,
)


# Helpers — write temp YAML config files

def _write_yaml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ===== Priority Tests =====

class TestConfigPriority:
    """Config resolution follows v0-scope.md §8 priority order."""

    def test_cli_overrides_everything(self, tmp_path):
        """CLI flags have highest priority."""
        proj = _write_yaml(tmp_path / "crossreview.yaml", """
reviewer_config:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
""")
        cfg = resolve_reviewer_config(
            cli_model="claude-sonnet-4-20250514",
            cli_provider="anthropic",
            cli_api_key_env="ANTHROPIC_API_KEY",
            project_config_path=proj,
        )
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"

    def test_project_yaml_over_user_yaml(self, tmp_path):
        """Project-level config beats user-level config."""
        proj = _write_yaml(tmp_path / "proj" / "crossreview.yaml", """
reviewer_config:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
""")
        user = _write_yaml(tmp_path / "user" / "config.yaml", """
reviewer_config:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
""")
        cfg = resolve_reviewer_config(
            project_config_path=proj,
            user_config_path=user,
        )
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.provider == "anthropic"

    def test_user_yaml_over_env(self, tmp_path, monkeypatch):
        """User-level config beats environment variables."""
        user = _write_yaml(tmp_path / "config.yaml", """
reviewer_config:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
""")
        monkeypatch.setenv("CROSSREVIEW_MODEL", "gpt-4o")
        monkeypatch.setenv("CROSSREVIEW_PROVIDER", "openai")
        monkeypatch.setenv("CROSSREVIEW_API_KEY_ENV", "OPENAI_API_KEY")
        cfg = resolve_reviewer_config(
            project_config_path=tmp_path / "nonexistent.yaml",
            user_config_path=user,
        )
        assert cfg.model == "claude-sonnet-4-20250514"

    def test_env_as_fallback(self, tmp_path, monkeypatch):
        """Environment variables work when no config files exist."""
        monkeypatch.setenv("CROSSREVIEW_MODEL", "gpt-4o")
        monkeypatch.setenv("CROSSREVIEW_PROVIDER", "openai")
        monkeypatch.setenv("CROSSREVIEW_API_KEY_ENV", "OPENAI_API_KEY")
        cfg = resolve_reviewer_config(
            project_config_path=tmp_path / "nonexistent.yaml",
            user_config_path=tmp_path / "nonexistent2.yaml",
        )
        assert cfg.model == "gpt-4o"
        assert cfg.provider == "openai"
        assert cfg.api_key_env == "OPENAI_API_KEY"


# ===== Partial Merge Tests =====

class TestConfigMerge:
    """Fields from different layers merge — each field resolved independently."""

    def test_model_from_cli_rest_from_yaml(self, tmp_path):
        """CLI provides model, yaml provides provider + api_key_env."""
        proj = _write_yaml(tmp_path / "crossreview.yaml", """
reviewer_config:
  provider: anthropic
  api_key_env: ANTHROPIC_API_KEY
""")
        cfg = resolve_reviewer_config(
            cli_model="claude-opus-4-20250514",
            project_config_path=proj,
            user_config_path=tmp_path / "nonexistent.yaml",
        )
        assert cfg.model == "claude-opus-4-20250514"
        assert cfg.provider == "anthropic"
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"

    def test_provider_from_env_rest_from_yaml(self, tmp_path, monkeypatch):
        """Cross-layer merge: provider from env, model + key from project yaml."""
        proj = _write_yaml(tmp_path / "crossreview.yaml", """
reviewer_config:
  model: claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
""")
        monkeypatch.setenv("CROSSREVIEW_PROVIDER", "anthropic")
        cfg = resolve_reviewer_config(
            project_config_path=proj,
            user_config_path=tmp_path / "nonexistent.yaml",
        )
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"


# ===== Error Tests =====

class TestConfigErrors:
    """ModelNotConfigured when resolution fails."""

    def test_no_config_at_all(self, tmp_path, monkeypatch):
        """No CLI, no yaml, no env → ModelNotConfigured."""
        # Clear any env vars that might leak
        monkeypatch.delenv("CROSSREVIEW_MODEL", raising=False)
        monkeypatch.delenv("CROSSREVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("CROSSREVIEW_API_KEY_ENV", raising=False)
        with pytest.raises(ModelNotConfigured):
            resolve_reviewer_config(
                project_config_path=tmp_path / "nonexistent.yaml",
                user_config_path=tmp_path / "nonexistent2.yaml",
            )

    def test_model_only_no_provider(self, tmp_path, monkeypatch):
        """Model without provider → ModelNotConfigured."""
        monkeypatch.delenv("CROSSREVIEW_MODEL", raising=False)
        monkeypatch.delenv("CROSSREVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("CROSSREVIEW_API_KEY_ENV", raising=False)
        with pytest.raises(ModelNotConfigured, match="provider"):
            resolve_reviewer_config(
                cli_model="claude-sonnet-4-20250514",
                project_config_path=tmp_path / "nonexistent.yaml",
                user_config_path=tmp_path / "nonexistent2.yaml",
            )

    def test_model_and_provider_no_key(self, tmp_path, monkeypatch):
        """Model + provider without api_key_env → ModelNotConfigured."""
        monkeypatch.delenv("CROSSREVIEW_MODEL", raising=False)
        monkeypatch.delenv("CROSSREVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("CROSSREVIEW_API_KEY_ENV", raising=False)
        with pytest.raises(ModelNotConfigured, match="api_key_env"):
            resolve_reviewer_config(
                cli_model="claude-sonnet-4-20250514",
                cli_provider="anthropic",
                project_config_path=tmp_path / "nonexistent.yaml",
                user_config_path=tmp_path / "nonexistent2.yaml",
            )

    def test_config_error_is_base(self):
        """ModelNotConfigured is a ConfigError."""
        assert issubclass(ModelNotConfigured, ConfigError)


# ===== Edge Cases =====

class TestConfigEdgeCases:
    """Config loading edge cases."""

    def test_empty_yaml_file(self, tmp_path, monkeypatch):
        """Empty yaml file should not crash, just provide no values."""
        monkeypatch.delenv("CROSSREVIEW_MODEL", raising=False)
        monkeypatch.delenv("CROSSREVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("CROSSREVIEW_API_KEY_ENV", raising=False)
        proj = _write_yaml(tmp_path / "crossreview.yaml", "")
        with pytest.raises(ModelNotConfigured):
            resolve_reviewer_config(
                project_config_path=proj,
                user_config_path=tmp_path / "nonexistent.yaml",
            )

    def test_malformed_yaml_structure(self, tmp_path, monkeypatch):
        """YAML with wrong structure (not a dict) should not crash."""
        monkeypatch.delenv("CROSSREVIEW_MODEL", raising=False)
        monkeypatch.delenv("CROSSREVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("CROSSREVIEW_API_KEY_ENV", raising=False)
        proj = _write_yaml(tmp_path / "crossreview.yaml", "just a string")
        with pytest.raises(ModelNotConfigured):
            resolve_reviewer_config(
                project_config_path=proj,
                user_config_path=tmp_path / "nonexistent.yaml",
            )

    def test_nonexistent_yaml_files(self, tmp_path, monkeypatch):
        """Non-existent yaml files should not crash."""
        monkeypatch.setenv("CROSSREVIEW_MODEL", "gpt-4o")
        monkeypatch.setenv("CROSSREVIEW_PROVIDER", "openai")
        monkeypatch.setenv("CROSSREVIEW_API_KEY_ENV", "OPENAI_API_KEY")
        cfg = resolve_reviewer_config(
            project_config_path=tmp_path / "nope.yaml",
            user_config_path=tmp_path / "also_nope.yaml",
        )
        assert cfg.model == "gpt-4o"
