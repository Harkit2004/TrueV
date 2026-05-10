from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from src.see_through_jobs import run_see_through_decompose_job
from src.see_through_runner import parse_inference_extra_args
from src.settings import get_settings
from src.stretchy_export import build_decompose_attachment_bytes


def create_see_through_worker_app() -> FastAPI:
    """Minimal GPU-side service: runs upstream inference_psd.py. Bind to 127.0.0.1 + SSH tunnel."""
    app = FastAPI(title="See-through worker (GPU)")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Cheap check that the process is listening (does not run inference)."""
        return {"status": "ok", "service": "see-through-worker"}

    @app.post("/decompose")
    async def decompose(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        group_offload: bool = Query(
            False,
            description="Lower VRAM (~10 GB at 1280); slower.",
        ),
        include_live2d: bool = Query(
            False,
            description="Also run Stretchy headless Live2D export (requires STRETCHY_STUDIO_ROOT + Node).",
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
            inference_extra_args=parse_inference_extra_args(
                settings.see_through_inference_extra_args
            ),
        )

        def rm_job(d: Path = job_dir) -> None:
            shutil.rmtree(d, ignore_errors=True)

        if include_live2d and settings.stretchy_studio_root is None:
            background_tasks.add_task(rm_job)
            raise HTTPException(
                status_code=503,
                detail="include_live2d requires STRETCHY_STUDIO_ROOT in the worker environment (.env).",
            )

        background_tasks.add_task(rm_job)

        try:
            body_out, fname_out, media_type = await build_decompose_attachment_bytes(
                stretchy_root=settings.stretchy_studio_root,
                node_bin=settings.node_bin,
                script_rel=settings.headless_export_script,
                stretchy_timeout_sec=settings.stretchy_export_timeout_sec,
                job_dir=job_dir,
                psd_path=psd_path,
                dl_name=dl_name,
                include_live2d=include_live2d,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return Response(
            content=body_out,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{fname_out}"'},
        )

    return app


app = create_see_through_worker_app()
