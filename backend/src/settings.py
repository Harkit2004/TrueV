from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    comfyui_base_url: str = Field(default="http://127.0.0.1:8188")
    anime_workflow_path: Path | None = Field(default=None)
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

    def anime_path(self) -> Path:
        return self.anime_workflow_path or (_repo_root() / "anime.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
