from __future__ import annotations

import json
import logging
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
from typing import Any, AsyncIterator

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from src.comfy_client import (
    fetch_view_bytes,
    pick_first_from_node,
    prepare_workflow_for_api,
    queue_prompt,
    wait_for_outputs,
)
from src.see_through_jobs import run_see_through_decompose_job
from src.see_through_proxy import proxy_decompose_to_remote
from src.settings import Settings, get_settings
from src.stretchy_export import build_decompose_attachment_bytes


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    log = logging.getLogger("uvicorn.error")
    s = get_settings()
    wf = s.lumina_workflow_path.expanduser()
    try:
        wf = wf.resolve()
    except OSError:
        pass
    log.info(
        "Lumina: comfy=%s workflow=%s workflow_exists=%s",
        s.comfyui_base_url,
        wf,
        wf.is_file(),
    )
    st_url = (s.see_through_service_url or "").strip()
    if st_url:
        log.info("See-through: requests proxied to worker at %s", st_url)
    elif s.see_through_repo is not None:
        log.info("See-through: local inference repo=%s", s.see_through_repo.expanduser())
    else:
        log.info(
            "See-through: not configured (set SEE_THROUGH_SERVICE_URL or SEE_THROUGH_REPO in backend/.env)"
        )
    st_root = s.stretchy_studio_root
    if st_root is not None:
        log.info("Stretchy headless: studio root=%s", st_root.expanduser())
    yield


def random_comfy_seed() -> int:
    """Lumina sampler: large seed OK."""
    return secrets.randbelow(2**63 - 1)


def build_view_url(filename: str, subfolder: str, file_type: str) -> str:
    q: dict[str, str] = {"filename": filename, "type": file_type}
    if subfolder:
        q["subfolder"] = subfolder
    return "/api/comfy/view?" + urlencode(q)


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20000)


class GenerateResponse(BaseModel):
    status: str = "ok"
    image_url: str


async def _run_lumina_pipeline(settings: Settings, body: GenerateRequest) -> dict[str, Any]:
    anime_path = settings.lumina_workflow_path.expanduser()
    try:
        anime_path = anime_path.resolve()
    except OSError:
        pass
    if not anime_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=(
                f"Missing Lumina workflow JSON: {anime_path}. "
                "Use repo-root anime.json or set LUMINA_WORKFLOW_PATH in backend/.env, then restart."
            ),
        )

    try:
        anime_wf = prepare_workflow_for_api(json.loads(anime_path.read_text(encoding="utf-8")))
        anime_wf["48:51"]["inputs"]["value"] = body.prompt.strip()
        anime_wf["48:33"]["inputs"]["seed"] = random_comfy_seed()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid workflow JSON in {anime_path}: {exc}",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Lumina workflow {anime_path} is missing node or field {exc!s} "
                "(expected KSampler seed and user prompt nodes). Re-export anime.json from ComfyUI."
            ),
        ) from exc

    try:
        async with httpx.AsyncClient(
            base_url=settings.comfyui_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.workflow_timeout_sec, connect=60.0),
        ) as client:
            pid = await queue_prompt(client, anime_wf)
            out = await wait_for_outputs(
                client,
                pid,
                poll_interval=settings.poll_interval_sec,
                timeout_sec=settings.workflow_timeout_sec,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Cannot reach ComfyUI at {settings.comfyui_base_url!r}: {exc}. "
                "Start ComfyUI and check COMFYUI_BASE_URL in backend/.env."
            ),
        ) from exc

    return pick_first_from_node(
        out,
        "9",
        extensions=(".png", ".jpg", ".jpeg", ".webp"),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Lumina ComfyUI API", lifespan=_lifespan)

    @app.exception_handler(HTTPException)
    async def _log_http_exceptions(request: Request, exc: HTTPException) -> JSONResponse:
        log = logging.getLogger("uvicorn.error")
        log.warning("%s %s -> %s %s", request.method, request.url.path, exc.status_code, exc.detail)
        hdrs = dict(exc.headers) if getattr(exc, "headers", None) else None
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder({"detail": exc.detail}),
            headers=hdrs,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def serve_index() -> FileResponse:
        index = STATIC_DIR / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=500, detail="Missing static/index.html")
        return FileResponse(index)

    @app.get("/api/comfy/view")
    async def proxy_comfy_view(
        filename: str = Query(...),
        type: str = Query("output"),
        subfolder: str = Query(""),
    ) -> Response:
        settings = get_settings()
        async with httpx.AsyncClient(
            base_url=settings.comfyui_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.workflow_timeout_sec, connect=60.0),
        ) as client:
            try:
                body = await fetch_view_bytes(
                    client,
                    filename=filename,
                    subfolder=subfolder,
                    file_type=type,
                )
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:2000],
                ) from exc
        lower = filename.lower()
        media = "application/octet-stream"
        if lower.endswith(".png"):
            media = "image/png"
        elif lower.endswith(".jpg") or lower.endswith(".jpeg"):
            media = "image/jpeg"
        elif lower.endswith(".webp"):
            media = "image/webp"
        return Response(content=body, media_type=media)

    @app.get("/api/debug/comfy/object_info/{class_type}")
    async def comfy_object_info(class_type: str) -> Any:
        """Inspect valid inputs/widgets for a node class from ComfyUI."""
        settings = get_settings()
        async with httpx.AsyncClient(
            base_url=settings.comfyui_base_url.rstrip("/"),
            timeout=httpx.Timeout(120.0, connect=30.0),
        ) as client:
            r = await client.get(f"/object_info/{class_type}")
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=r.text[:4000])
            return r.json()

    @app.post("/api/generate", response_model=GenerateResponse)
    async def api_generate(body: GenerateRequest) -> GenerateResponse:
        settings = get_settings()
        try:
            lumina_item = await _run_lumina_pipeline(settings, body)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Lumina workflow must expose the final image on Save Image node id 9; ComfyUI outputs: {exc}. "
                    "Re-export anime.json if your graph changed."
                ),
            ) from exc

        image_url = build_view_url(
            str(lumina_item["filename"]),
            str(lumina_item.get("subfolder") or ""),
            str(lumina_item.get("type") or "output"),
        )
        return GenerateResponse(image_url=image_url)

    @app.post("/api/see-through/decompose", response_model=None)
    async def api_see_through_decompose(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        group_offload: bool = Query(
            False,
            description="Lower VRAM (~10 GB at 1280); slower. See upstream README.",
        ),
        include_live2d: bool = Query(
            False,
            description="Bundle PSD + Stretchy Live2D (.cmo3 in zip). Worker needs STRETCHY_STUDIO_ROOT + Node.",
        ),
    ) -> Response:
        """
        See-through PSD decomposition via GPU worker HTTP API (recommended + SSH tunnel),
        or same-machine SEE_THROUGH_REPO subprocess fallback.
        """
        settings = get_settings()
        body = await file.read()
        if not body:
            raise HTTPException(status_code=400, detail="Empty file.")
        raw_name = (file.filename or "image").strip()

        service_url = (settings.see_through_service_url or "").strip()
        if include_live2d and not service_url and settings.stretchy_studio_root is None:
            raise HTTPException(
                status_code=503,
                detail="include_live2d requires STRETCHY_STUDIO_ROOT when running See-through locally (no SEE_THROUGH_SERVICE_URL).",
            )

        if service_url:
            try:
                body_out, fname_out, mt = await proxy_decompose_to_remote(
                    service_base_url=service_url,
                    secret=settings.see_through_service_secret,
                    file_body=body,
                    upload_filename=raw_name or "image.png",
                    group_offload=group_offload,
                    include_live2d=include_live2d,
                    timeout_sec=settings.see_through_timeout_sec,
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return Response(
                content=body_out,
                media_type=mt,
                headers={"Content-Disposition": f'attachment; filename="{fname_out}"'},
            )

        if settings.see_through_repo is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "See-through is not configured. Set SEE_THROUGH_SERVICE_URL to your SSH-forwarded "
                    "worker (see notes.txt), or set SEE_THROUGH_REPO + SEE_THROUGH_PYTHON on this machine."
                ),
            )

        repo = settings.see_through_repo.expanduser().resolve()
        job_dir, psd_path, dl_name = await run_see_through_decompose_job(
            file_body=body,
            raw_filename=raw_name,
            group_offload=group_offload,
            repo=repo,
            python_exe=settings.see_through_python,
            timeout_sec=settings.see_through_timeout_sec,
        )

        def cleanup_job(d: Path = job_dir) -> None:
            shutil.rmtree(d, ignore_errors=True)

        background_tasks.add_task(cleanup_job)

        try:
            body_out, fname_out, mt = await build_decompose_attachment_bytes(
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

        return Response(
            content=body_out,
            media_type=mt,
            headers={"Content-Disposition": f'attachment; filename="{fname_out}"'},
        )

    return app


app = create_app()
