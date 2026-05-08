from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from src.see_through_jobs import run_see_through_decompose_job
from src.settings import get_settings


def create_see_through_worker_app() -> FastAPI:
    """Minimal GPU-side service: runs upstream inference_psd.py. Bind to 127.0.0.1 + SSH tunnel."""
    app = FastAPI(title="See-through worker (GPU)")

    @app.post("/decompose")
    async def decompose(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        group_offload: bool = Query(
            False,
            description="Lower VRAM (~10 GB at 1280); slower.",
        ),
        x_see_through_secret: str | None = Header(None, alias="X-See-Through-Secret"),
    ):
        settings = get_settings()
        expected = settings.see_through_service_secret
        if expected and x_see_through_secret != expected:
            raise HTTPException(status_code=401, detail="Invalid X-See-Through-Secret")

        if settings.see_through_repo is None:
            raise HTTPException(
                status_code=503,
                detail="Worker misconfigured: set SEE_THROUGH_REPO (clone path on this machine).",
            )

        repo = settings.see_through_repo.expanduser().resolve()
        body = await file.read()
        raw_name = (file.filename or "image").strip()

        job_dir, psd_path, dl_name = await run_see_through_decompose_job(
            file_body=body,
            raw_filename=raw_name,
            group_offload=group_offload,
            repo=repo,
            python_exe=settings.see_through_python,
            timeout_sec=settings.see_through_timeout_sec,
        )

        def rm_job(d: Path = job_dir) -> None:
            shutil.rmtree(d, ignore_errors=True)

        background_tasks.add_task(rm_job)

        return FileResponse(
            path=str(psd_path),
            filename=dl_name,
            media_type="application/octet-stream",
        )

    return app


app = create_see_through_worker_app()
