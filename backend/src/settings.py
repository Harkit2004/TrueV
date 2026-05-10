import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    return _BACKEND_DIR.parent


def _default_lumina_workflow() -> Path:
    return _repo_root() / "anime.json"


def _parse_lumina_workflow_path(v: Any) -> Path:
    """Normalize paths from env (quotes, normpath). Relative paths are anchored to repo root."""
    if v is None or v == "":
        v = _default_lumina_workflow()
    if isinstance(v, Path):
        p = v
    else:
        s = str(v).strip().strip('"').strip("'")
        p = Path(os.path.normpath(s))
    if not p.is_absolute():
        p = (_repo_root() / p).resolve()
    else:
        p = p.expanduser().resolve()
    return p


def _parse_optional_repo_path(v: Any) -> Path | None:
    """Relative paths anchor to repo root; empty means None."""
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, Path):
        p = v
    else:
        s = str(v).strip().strip('"').strip("'")
        p = Path(os.path.normpath(s))
    if not p.is_absolute():
        p = (_repo_root() / p).resolve()
    else:
        p = p.expanduser().resolve()
    return p


StretchyStudioRoot = Annotated[Path | None, BeforeValidator(_parse_optional_repo_path)]


LuminaWorkflowPath = Annotated[Path, BeforeValidator(_parse_lumina_workflow_path)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    comfyui_base_url: str = Field(default="http://127.0.0.1:8188")
    lumina_workflow_path: LuminaWorkflowPath = Field(
        default_factory=_default_lumina_workflow,
        description="Lumina workflow JSON. Env: LUMINA_WORKFLOW_PATH. Use forward slashes in .env on Windows.",
    )
    poll_interval_sec: float = Field(default=1.0)
    workflow_timeout_sec: float = Field(default=7200.0)

    see_through_service_url: str | None = Field(
        default=None,
        description=(
            "HTTP base URL of the See-through worker (GPU machine). "
            "On your laptop use http://127.0.0.1:<port> with SSH -L forwarding."
        ),
    )
    see_through_service_secret: str | None = Field(
        default=None,
        description="If set, worker requires matching X-See-Through-Secret; client sends same value.",
    )

    see_through_repo: Path | None = Field(
        default=None,
        description=(
            "On the GPU worker only: root of https://github.com/shitagaki-lab/see-through "
            "with its requirements installed. Optional on laptop if SEE_THROUGH_SERVICE_URL is set."
        ),
    )
    see_through_python: str = Field(
        default="python",
        description="Python from the See-through conda env (worker host).",
    )
    see_through_timeout_sec: float = Field(default=7200.0)
    see_through_inference_extra_args: str = Field(
        default="",
        description=(
            "Extra CLI tokens appended to inference_psd.py (worker/local). "
            "Shell-style quoting via shlex; env: SEE_THROUGH_INFERENCE_EXTRA_ARGS."
        ),
    )

    stretchy_studio_root: StretchyStudioRoot = Field(
        default=None,
        description=(
            "Path to stretchystudio repo (npm install + canvas). "
            "GPU worker: required for include_live2d=1 on /api/see-through/decompose."
        ),
    )
    node_bin: str = Field(default="node", description="Node executable for headless Live2D export.")
    headless_export_script: str = Field(
        default="scripts/headless_live2d_export.mjs",
        description="Relative to stretchy_studio_root.",
    )
    stretchy_export_timeout_sec: float = Field(
        default=7200.0,
        description="Timeout for node headless Live2D subprocess.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
