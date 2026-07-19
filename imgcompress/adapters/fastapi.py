import functools
from io import BytesIO
from pathlib import Path

from PIL import Image
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from ..config import DEFAULT_CONFIG
from ..core import compress

_COMPRESS_KEYS = ("quality", "max_width", "max_height", "fmt", "max_file_size")

_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
          "BMP": "image/bmp", "TIFF": "image/tiff", "GIF": "image/gif", "HEIF": "image/heif"}
_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
         "BMP": ".bmp", "TIFF": ".tiff", "GIF": ".gif", "HEIF": ".heic"}


def _describe(data: bytes, original_filename: str | None) -> tuple[str, str]:
    """คืน (filename, content_type) ให้ตรงกับ format จริงของ bytes หลังบีบ

    compress() อาจคืนของเดิมเป๊ะๆ (passthrough) หรือแปลง format ไปเลยก็ได้ —
    เช็คจากเนื้อไฟล์จริงเสมอ ไม่เดาจาก fmt setting เพื่อให้ถูกต้องทุกเคส
    """
    try:
        fmt = Image.open(BytesIO(data)).format
    except Exception:
        fmt = None
    if fmt not in _MIME:
        return original_filename or "file", "application/octet-stream"
    stem = Path(original_filename).stem if original_filename else "file"
    return f"{stem}{_EXT[fmt]}", _MIME[fmt]


async def _compress_upload(value: UploadFile, kwargs: dict) -> UploadFile:
    data = await run_in_threadpool(compress, value, **kwargs)  # Pillow เป็น sync, offload ไม่ให้บล็อก event loop
    filename, content_type = _describe(data, value.filename)
    return UploadFile(
        BytesIO(data), size=len(data), filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def CompressUpload(**overrides):
    settings = {**DEFAULT_CONFIG, **overrides}
    kwargs = {k: settings[k] for k in _COMPRESS_KEYS}

    def decorator(handler):
        @functools.wraps(handler)
        async def wrapper(*args, **fn_kwargs):
            for key, value in list(fn_kwargs.items()):
                if isinstance(value, UploadFile):
                    fn_kwargs[key] = await _compress_upload(value, kwargs)
                elif isinstance(value, list) and any(isinstance(v, UploadFile) for v in value):
                    fn_kwargs[key] = [
                        await _compress_upload(v, kwargs) if isinstance(v, UploadFile) else v
                        for v in value
                    ]
            return await handler(*args, **fn_kwargs)

        return wrapper

    return decorator


class ImgCompress:
    """Pure ASGI middleware: แก้ไข multipart request body ที่มีรูป → compress → ส่งต่อให้ route.

    ไม่ใช้ BaseHTTPMiddleware เพราะ call_next ไม่อ่าน receive ที่เราแทนที่
    (พิสูจน์แล้วว่า 422 กับ FastAPI จริง) — pure ASGI ใช้แต่ public interface

    ponytail: rebuild multipart ด้วยมือ — ครอบคลุมเคสทั่วไป ไม่รองรับ nested
    multipart หรือ header เพิ่มเติมต่อ part, ขยายทีหลังถ้าเจอเคสจริง
    """

    def __init__(self, app, **overrides):
        self.app = app
        settings = {**DEFAULT_CONFIG, **overrides}
        self._kwargs = {k: settings[k] for k in _COMPRESS_KEYS}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        content_type = Headers(scope=scope).get("content-type", "")
        if not content_type.startswith("multipart/form-data") or "boundary=" not in content_type:
            return await self.app(scope, receive, send)

        chunks = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        raw_body = b"".join(chunks)

        async def replay():
            return {"type": "http.request", "body": raw_body, "more_body": False}

        form = await Request(scope, replay).form()
        boundary = content_type.split("boundary=", 1)[1].strip('"')
        new_body = await _rebuild_multipart(form, boundary, self._kwargs)

        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-length"]
        scope["headers"].append((b"content-length", str(len(new_body)).encode()))

        sent = False

        async def new_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": new_body, "more_body": False}
            return await receive()  # ส่งต่อ message ถัดไป เช่น http.disconnect

        await self.app(scope, new_receive, send)


async def _rebuild_multipart(form, boundary: str, compress_kwargs: dict) -> bytes:
    boundary_bytes = boundary.encode()
    body = bytearray()
    for key, value in form.multi_items():
        body += b"--" + boundary_bytes + b"\r\n"
        if isinstance(value, UploadFile):
            data = await run_in_threadpool(compress, value, **compress_kwargs)  # ไม่บล็อก event loop
            filename, content_type = _describe(data, value.filename)  # content-type/นามสกุลต้องตรง format จริงหลังบีบ
            body += (
                f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            body += data
        else:
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}'.encode()
        body += b"\r\n"
    body += b"--" + boundary_bytes + b"--\r\n"
    return bytes(body)
