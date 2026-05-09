from __future__ import annotations

import asyncio
import io
import shutil
import zipfile
from pathlib import Path


def resolve_node_executable(node_bin: str) -> str:
    """
    Bare names are resolved with PATH; absolute paths must exist.
    Avoids opaque errno 2 from asyncio.create_subprocess_exec when `node` is missing from PATH.
    """
    raw = (node_bin or "").strip() or "node"
    p = Path(raw).expanduser()
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(raw)
    if found:
        return found
    raise RuntimeError(
        f"Node.js executable not found: {node_bin!r}. Install Node 20+ or set NODE_BIN to the "
        "full path (e.g. $(which node) or /usr/bin/node on Linux)."
    )


async def run_headless_live2d_export(
    *,
    stretchy_root: Path | None,
    node_bin: str,
    script_rel: str,
    psd_path: Path,
    out_path: Path,
    model_name: str,
    timeout_sec: float,
) -> None:
    """Run `node scripts/headless_live2d_export.mjs` inside STRETCHY_STUDIO_ROOT."""
    if stretchy_root is None:
        raise RuntimeError("STRETCHY_STUDIO_ROOT is not set")
    root = stretchy_root.expanduser().resolve()
    script = root / script_rel
    if not script.is_file():
        raise FileNotFoundError(f"Headless export script missing: {script}")
    node = resolve_node_executable(node_bin)
    cmd: list[str] = [
        node,
        str(script),
        "--psd-in",
        str(psd_path),
        "--zip-out",
        str(out_path),
        "--model-name",
        model_name,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Cannot spawn Node for Live2D export ({node}): install Node or fix NODE_BIN. {exc}"
        ) from exc
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(
            f"Headless Live2D export exceeded {timeout_sec}s"
        ) from None
    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        out = (stdout or b"").decode("utf-8", errors="replace").strip()
        detail = err or out or f"exit {proc.returncode}"
        raise RuntimeError(f"Headless Live2D export failed: {detail}")


async def build_decompose_attachment_bytes(
    *,
    stretchy_root: Path | None,
    node_bin: str,
    script_rel: str,
    stretchy_timeout_sec: float,
    job_dir: Path,
    psd_path: Path,
    dl_name: str,
    include_live2d: bool,
) -> tuple[bytes, str, str]:
    """
    Returns (body, filename_for_content_disposition, media_type).
    """
    base = Path(dl_name).stem or "see_through"
    if not include_live2d:
        data = psd_path.read_bytes()
        return data, dl_name, "application/octet-stream"

    if stretchy_root is None:
        raise RuntimeError(
            "include_live2d requires STRETCHY_STUDIO_ROOT (Stretchy Studio repo with npm install)."
        )
    live2d_path = job_dir / "_live2d_model.cmo3"
    await run_headless_live2d_export(
        stretchy_root=stretchy_root,
        node_bin=node_bin,
        script_rel=script_rel,
        psd_path=psd_path,
        out_path=live2d_path,
        model_name=base,
        timeout_sec=stretchy_timeout_sec,
    )
    zip_bytes = build_see_through_live2d_zip(
        psd_path=psd_path,
        live2d_artifact=live2d_path,
        base_name=base,
    )
    bundle_name = f"{base}_see_through_live2d.zip"
    return zip_bytes, bundle_name, "application/zip"


def build_see_through_live2d_zip(
    *,
    psd_path: Path,
    live2d_artifact: Path,
    base_name: str,
) -> bytes:
    """Single download: PSD + Live2D blob (usually .cmo3) under live2d/."""
    ext = live2d_artifact.suffix if live2d_artifact.suffix else ".cmo3"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(psd_path, arcname=f"{base_name}.psd")
        zf.write(live2d_artifact, arcname=f"live2d/{base_name}{ext}")
    return buf.getvalue()
