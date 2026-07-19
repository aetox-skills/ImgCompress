import functools
from io import BytesIO

from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from ..config import DEFAULT_CONFIG
from ..core import compress

_COMPRESS_KEYS = ("quality", "max_width", "max_height", "fmt")


def CompressUpload(**overrides):
    settings = {**DEFAULT_CONFIG, **overrides}
    kwargs = {k: settings[k] for k in _COMPRESS_KEYS}

    def decorator(handler):
        @functools.wraps(handler)
        async def wrapper(*args, **fn_kwargs):
            for key, value in list(fn_kwargs.items()):
                if isinstance(value, UploadFile):
                    fn_kwargs[key] = BytesIO(compress(value, **kwargs))
                elif isinstance(value, list) and any(isinstance(v, UploadFile) for v in value):
                    fn_kwargs[key] = [
                        BytesIO(compress(v, **kwargs)) if isinstance(v, UploadFile) else v
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
        new_body = _rebuild_multipart(form, boundary, self._kwargs)

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


def _rebuild_multipart(form, boundary: str, compress_kwargs: dict) -> bytes:
    boundary_bytes = boundary.encode()
    body = bytearray()
    for key, value in form.multi_items():
        body += b"--" + boundary_bytes + b"\r\n"
        if isinstance(value, UploadFile):
            data = compress(value, **compress_kwargs)
            body += (
                f'Content-Disposition: form-data; name="{key}"; filename="{value.filename}"\r\n'
                f"Content-Type: {value.content_type}\r\n\r\n"
            ).encode()
            body += data
        else:
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}'.encode()
        body += b"\r\n"
    body += b"--" + boundary_bytes + b"--\r\n"
    return bytes(body)
