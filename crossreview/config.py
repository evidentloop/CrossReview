"""CrossReview configuration loading.

Resolution order (v0-scope.md §8 Model Resolution):
  1. CLI flags (--model, --provider)
  2. ./crossreview.yaml (project-level)
  3. ~/.crossreview/config.yaml (user-level)
  4. CROSSREVIEW_MODEL / CROSSREVIEW_PROVIDER / CROSSREVIEW_API_KEY_ENV env vars
  5. Fail with MODEL_NOT_CONFIGURED

Core receives a resolved ReviewerConfig {provider, model, api_key_env}.
Core never picks defaults — that's the adapter's job.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# pyyaml is a runtime dependency (pyproject.toml) — import unconditionally.
# If missing, fail loudly rather than silently ignoring YAML config files,
# which would break the documented config priority chain.
import yaml

from crossreview.schema import ReviewerConfig


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when configuration resolution fails."""


class ModelNotConfigured(ConfigError):
    """No model could be resolved from any source."""


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

# Default file paths
_PROJECT_CONFIG = Path("crossreview.yaml")
_USER_CONFIG = Path.home() / ".crossreview" / "config.yaml"

# Environment variable names
_ENV_MODEL = "CROSSREVIEW_MODEL"
_ENV_PROVIDER = "CROSSREVIEW_PROVIDER"
_ENV_API_KEY_ENV = "CROSSREVIEW_API_KEY_ENV"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML config file. Returns empty dict if file does not exist."""
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _get_nested(d: dict, *keys: str) -> str | None:
    """Traverse nested dict keys, return str value or None."""
    current: Any = d
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return str(current) if current is not None else None


@dataclass
class _RawConfig:
    """Intermediate container — partially resolved, may have None fields."""
    provider: str | None = None
    model: str | None = None
    api_key_env: str | None = None

    def merge(self, other: "_RawConfig") -> "_RawConfig":
        """Fill None fields from other (lower-priority source)."""
        return _RawConfig(
            provider=self.provider or other.provider,
            model=self.model or other.model,
            api_key_env=self.api_key_env or other.api_key_env,
        )

    @property
    def is_complete(self) -> bool:
        return all([self.provider, self.model, self.api_key_env])


def _from_cli(
    model: str | None = None,
    provider: str | None = None,
    api_key_env: str | None = None,
) -> _RawConfig:
    return _RawConfig(provider=provider, model=model, api_key_env=api_key_env)


def _from_yaml(path: Path) -> _RawConfig:
    data = _load_yaml(path)
    return _RawConfig(
        provider=_get_nested(data, "reviewer_config", "provider"),
        model=_get_nested(data, "reviewer_config", "model"),
        api_key_env=_get_nested(data, "reviewer_config", "api_key_env"),
    )


def _from_env() -> _RawConfig:
    return _RawConfig(
        provider=os.environ.get(_ENV_PROVIDER),
        model=os.environ.get(_ENV_MODEL),
        api_key_env=os.environ.get(_ENV_API_KEY_ENV),
    )


def resolve_reviewer_config(
    *,
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_api_key_env: str | None = None,
    project_config_path: Path | None = None,
    user_config_path: Path | None = None,
) -> ReviewerConfig:
    """Resolve a ReviewerConfig from all sources in priority order.

    Priority (highest first):
      1. CLI flags
      2. Project-level crossreview.yaml
      3. User-level ~/.crossreview/config.yaml
      4. Environment variables

    Raises ModelNotConfigured if model cannot be resolved from any source.
    """
    layers = [
        _from_cli(model=cli_model, provider=cli_provider, api_key_env=cli_api_key_env),
        _from_yaml(project_config_path or _PROJECT_CONFIG),
        _from_yaml(user_config_path or _USER_CONFIG),
        _from_env(),
    ]

    merged = _RawConfig()
    for layer in layers:
        merged = merged.merge(layer)

    if not merged.model:
        raise ModelNotConfigured(
            "No model configured. Set via --model flag, crossreview.yaml, "
            "~/.crossreview/config.yaml, or CROSSREVIEW_MODEL env var."
        )
    if not merged.provider:
        raise ModelNotConfigured(
            "No provider configured. Set via --provider flag, crossreview.yaml, "
            "~/.crossreview/config.yaml, or CROSSREVIEW_PROVIDER env var."
        )
    if not merged.api_key_env:
        raise ModelNotConfigured(
            "No api_key_env configured. Set via crossreview.yaml, "
            "~/.crossreview/config.yaml, or CROSSREVIEW_API_KEY_ENV env var."
        )

    return ReviewerConfig(
        provider=merged.provider,
        model=merged.model,
        api_key_env=merged.api_key_env,
    )
