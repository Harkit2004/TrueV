from __future__ import annotations

import httpx


async def proxy_decompose_to_remote(
    *,
    service_base_url: str,
    secret: str | None,
    file_body: bytes,
    upload_filename: str,
    group_offload: bool,
    include_live2d: bool,
    timeout_sec: float,
) -> tuple[bytes, str, str]:
    """POST multipart to the GPU worker; returns (body_bytes, filename_for_client, media_type)."""
    headers: dict[str, str] = {}
    if secret:
        headers["X-See-Through-Secret"] = secret

    timeout = httpx.Timeout(timeout_sec, connect=120.0)
    async with httpx.AsyncClient(base_url=service_base_url.rstrip("/"), timeout=timeout) as client:
        files = {
            "file": (
                upload_filename or "image.png",
                file_body,
                "application/octet-stream",
            )
        }
        try:
            r = await client.post(
                "/decompose",
                params={
                    "group_offload": str(group_offload).lower(),
                    "include_live2d": str(include_live2d).lower(),
                },
                files=files,
                headers=headers,
            )
        except httpx.RequestError as exc:
            raise RuntimeError(f"See-through worker unreachable: {exc}") from exc

    if r.status_code >= 400:
        detail = r.text[:4000] if r.text else r.reason_phrase
        raise RuntimeError(f"See-through worker HTTP {r.status_code}: {detail}")

    cd = r.headers.get("content-disposition") or ""
    fname = "see_through.psd"
    if "filename=" in cd:
        part = cd.split("filename=", 1)[1].strip().strip('"').split(";")[0].strip()
        if part:
            fname = part

    mt = (r.headers.get("content-type") or "").split(";")[0].strip() or "application/octet-stream"
    return r.content, fname, mt
