"""Integration self-check กับ FastAPI จริง: python test_fastapi.py"""
import threading
from io import BytesIO

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile as StarletteUploadFile

from imgcompress import CompressUpload, ImgCompress
from imgcompress.adapters import fastapi as adapter


def _make_jpeg(w=3000, h=2000) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (200, 100, 50)).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _make_png(w=1000, h=800) -> bytes:
    import random

    random.seed(3)
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 255)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()  # noisy -> JPEG re-encode จะเล็กกว่า PNG จริง ทำให้ format แปลงจริง


def test_middleware():
    app = FastAPI()
    app.add_middleware(ImgCompress, quality=75)

    @app.post("/upload")
    async def upload(file: UploadFile = File(...), note: str = Form(...)):
        data = await file.read()
        img = Image.open(BytesIO(data))
        return {"size": len(data), "w": img.width, "h": img.height,
                "filename": file.filename, "content_type": file.content_type, "note": note}

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    client = TestClient(app)
    original = _make_jpeg()
    r = client.post("/upload",
                    files={"file": ("photo.jpg", original, "image/jpeg")},
                    data={"note": "hello"})
    body = r.json()
    assert r.status_code == 200
    assert body["size"] < len(original), "middleware ต้องทำให้ไฟล์เล็กลง"
    assert body["w"] <= 1920 and body["h"] <= 1080
    assert body["note"] == "hello", "form field อื่นต้องรอดจากการ rebuild"
    assert body["filename"] == "photo.jpg"
    assert body["content_type"] == "image/jpeg"
    assert client.get("/plain").json() == {"ok": True}, "request ที่ไม่ใช่ multipart ต้องผ่านเฉยๆ"


def test_middleware_metadata_matches_real_output_format():
    """PNG -> JPEG (default fmt) ต้องได้ filename/content-type เป็น jpeg จริง ไม่ใช่ png เดิม"""
    app = FastAPI()
    app.add_middleware(ImgCompress, quality=75)

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)):
        return {"filename": file.filename, "content_type": file.content_type}

    client = TestClient(app)
    r = client.post("/upload", files={"file": ("photo.png", _make_png(), "image/png")})
    body = r.json()
    assert r.status_code == 200
    assert body["filename"] == "photo.jpg", f"นามสกุลต้องตรง format จริง: {body}"
    assert body["content_type"] == "image/jpeg", f"content-type ต้องตรง format จริง: {body}"


def test_decorator_preserves_uploadfile_contract():
    """file: UploadFile ต้องยังเป็น UploadFile จริง ใช้ .filename/.content_type/.read() ได้"""
    app = FastAPI()

    @app.post("/upload")
    @CompressUpload(quality=75)
    async def upload(file: UploadFile = File(...)):
        assert isinstance(file, StarletteUploadFile)
        data = await file.read()
        img = Image.open(BytesIO(data))
        return {"w": img.width, "h": img.height,
                "filename": file.filename, "content_type": file.content_type}

    client = TestClient(app)
    r = client.post("/upload", files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")})
    body = r.json()
    assert r.status_code == 200 and body["w"] <= 1920
    assert body["filename"] == "photo.jpg"
    assert body["content_type"] == "image/jpeg"


def test_decorator_metadata_matches_real_output_format():
    app = FastAPI()

    @app.post("/upload")
    @CompressUpload(quality=75)
    async def upload(file: UploadFile = File(...)):
        return {"filename": file.filename, "content_type": file.content_type}

    client = TestClient(app)
    r = client.post("/upload", files={"file": ("photo.png", _make_png(), "image/png")})
    body = r.json()
    assert body["filename"] == "photo.jpg", f"นามสกุลต้องตรง format จริง: {body}"
    assert body["content_type"] == "image/jpeg", f"content-type ต้องตรง format จริง: {body}"


def test_middleware_skips_buffering_over_content_length_cap():
    """content-length เกิน max_file_size ต้องข้ามไปเลย ไม่ buffer body เองซ้ำ"""
    import asyncio

    async def run():
        body = _make_jpeg()
        receive_calls = []

        async def receive():
            receive_calls.append(1)
            return {"type": "http.request", "body": body, "more_body": False}

        downstream_reads = []

        async def downstream_app(scope, receive, send):
            downstream_reads.append(await receive())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = ImgCompress(downstream_app, max_file_size=1000)  # เล็กกว่า _make_jpeg() มากแน่ๆ
        scope = {
            "type": "http",
            "headers": [
                (b"content-type", b"multipart/form-data; boundary=X"),
                (b"content-length", str(len(body)).encode()),
            ],
        }

        async def send(message):
            pass

        await mw(scope, receive, send)
        assert len(receive_calls) == 1, "middleware ต้องไม่วน receive() เพื่อ buffer เอง เมื่อรู้อยู่แล้วว่าเกิน max_file_size"
        assert downstream_reads[0]["body"] == body, "ต้องส่ง body เดิมตรงๆ ให้ downstream อ่านเอง"

    asyncio.run(run())


def test_compress_runs_off_event_loop():
    """compress() ต้องรันใน threadpool ไม่ใช่ inline บน event loop thread"""
    main_thread_id = threading.get_ident()
    seen_thread_ids = []

    real_compress = adapter.compress

    def spy(*args, **kwargs):
        seen_thread_ids.append(threading.get_ident())
        return real_compress(*args, **kwargs)

    adapter.compress = spy
    try:
        app = FastAPI()

        @app.post("/upload")
        @CompressUpload(quality=75)
        async def upload(file: UploadFile = File(...)):
            return {"ok": True}

        client = TestClient(app)
        r = client.post("/upload", files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")})
        assert r.status_code == 200
        assert seen_thread_ids, "compress ต้องถูกเรียก"
        assert main_thread_id not in seen_thread_ids, "compress ต้องไม่รันบน thread เดียวกับ event loop"
    finally:
        adapter.compress = real_compress


if __name__ == "__main__":
    test_middleware()
    test_middleware_metadata_matches_real_output_format()
    test_decorator_preserves_uploadfile_contract()
    test_decorator_metadata_matches_real_output_format()
    test_middleware_skips_buffering_over_content_length_cap()
    test_compress_runs_off_event_loop()
    print("ok")
