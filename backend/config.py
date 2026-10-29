"""Explicit, side-effect-free settings (AI-assisted from docs/llm-integration.md).

No config file is read on import. A YAML file is read only when explicitly
passed to from_sources; None means environment/defaults only. Unknown YAML keys
(including the existing Lexmount credentials) are ignored, not retained.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from backend.schemas import AppError

REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)

    deepseek_api_key: SecretStr | None = Field(default=None, repr=False)
    llm_model: str = Field(default="deepseek/deepseek-chat", min_length=1)
    llm_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(default=4096, gt=0, le=4096)
    request_timeout_seconds: float = Field(default=120, gt=0, le=120, allow_inf_nan=False)
    max_model_calls: Annotated[int, Field(strict=True, gt=0, le=5)] = 5
    max_tool_calls: Annotated[int, Field(strict=True, gt=0, le=8)] = 8
    num_retries: Literal[0] = 0
    data_dir: Path = REPO_ROOT / "data"
    catalog_path: Path = REPO_ROOT / "data" / "competitions.json"
    allowed_origins: list[str] = Field(default_factory=list)

    @field_validator("deepseek_api_key", mode="before")
    @classmethod
    def normalize_empty_key(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "llm_timeout_seconds", "llm_max_output_tokens", "request_timeout_seconds", mode="before"
    )
    @classmethod
    def reject_boolean_limit(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Limits must be positive numbers.")
        return value

    @field_validator("data_dir", "catalog_path", mode="before")
    @classmethod
    def resolve_repo_path(cls, value: Any) -> Path:
        path = Path(value).expanduser()
        return (REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("CORS requires explicit HTTP(S) origins without paths.")
            # Accessing port also rejects malformed or out-of-range ports.
            _ = parsed.port
        return origins

    @classmethod
    def from_sources(
        cls,
        environ: Mapping[str, str],
        config_path: Path | None,
    ) -> "Settings":
        """Environment wins even when empty; failures never echo source values."""
        try:
            source: dict[str, Any] = {}
            if config_path is not None:
                path = config_path if config_path.is_absolute() else REPO_ROOT / config_path
                with path.open(encoding="utf-8") as stream:
                    loaded = yaml.safe_load(stream)
                if loaded is not None and not isinstance(loaded, dict):
                    raise ValueError("Configuration must be a mapping.")
                source = loaded or {}

            values: dict[str, Any] = {}
            for field, env_key, yaml_key in (
                ("deepseek_api_key", "DEEPSEEK_API_KEY", "deepseek-api-key"),
                ("llm_model", "LLM_MODEL", "llm-model"),
                ("llm_timeout_seconds", "LLM_TIMEOUT_SECONDS", "llm-timeout-seconds"),
                ("llm_max_output_tokens", "LLM_MAX_OUTPUT_TOKENS", "llm-max-output-tokens"),
                ("data_dir", "BJTU_DATA_DIR", "bjtu-data-dir"),
                ("catalog_path", "BJTU_CATALOG_PATH", "bjtu-catalog-path"),
                ("allowed_origins", "BJTU_ALLOWED_ORIGINS", "bjtu-allowed-origins"),
            ):
                if env_key in environ:
                    values[field] = environ[env_key]
                elif yaml_key in source:
                    values[field] = source[yaml_key]
            if isinstance(values.get("allowed_origins"), str):
                values["allowed_origins"] = [
                    item.strip() for item in values["allowed_origins"].split(",") if item.strip()
                ]
            return cls.model_validate(values)
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError, TypeError):
            raise AppError("CONFIG_INVALID", "后端配置无效，请检查配置。", 500) from None
