from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException

from src.see_through_runner import expected_psd_path, inference_script_path, run_inference_psd

_ALLOWED_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})


async def run_see_through_decompose_job(
    *,
    file_body: bytes,
    raw_filename: str,
    group_offload: bool,
    repo: Path,
    python_exe: str,
    timeout_sec: float,
) -> tuple[Path, Path, str]:
    """
    Run inference in a temp directory. Returns (job_dir, psd_path, suggested_download_name).
    Caller must remove job_dir when done (e.g. BackgroundTasks).
    """
    script = inference_script_path(repo)
    if not script.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"SEE_THROUGH_REPO is invalid (missing {script}).",
        )

    name = (raw_filename or "image").strip()
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        suffix = ".png"

    job_dir = Path(tempfile.mkdtemp(prefix="see_through_"))
    src_path = job_dir / f"input{suffix}"

    if not file_body:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Empty file.")
    src_path.write_bytes(file_body)

    stem = src_path.stem

    try:
        await run_inference_psd(
            repo=repo,
            python_exe=python_exe,
            src_image=src_path,
            save_dir=job_dir,
            timeout_sec=timeout_sec,
            group_offload=group_offload,
        )
    except TimeoutError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    psd = expected_psd_path(job_dir, stem)
    if not psd.is_file():
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=502,
            detail=f"See-through finished but PSD was not found at {psd}",
        )

    out_name = Path(name).stem or "see_through"
    return job_dir, psd, f"{out_name}.psd"
