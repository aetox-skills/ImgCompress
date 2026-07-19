"""Integration self-check กับ FastAPI จริง: python test_fastapi.py"""
from io import BytesIO

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from imgcompress import CompressUpload, ImgCompress


def _make_jpeg(w=3000, h=2000) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (200, 100, 50)).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_middleware():
    app = FastAPI()
    app.add_middleware(ImgCompress, quality=75)

    @app.post("/upload")
    async def upload(file: UploadFile = File(...), note: str = Form(...)):
        data = await file.read()
        img = Image.open(BytesIO(data))
        return {"size": len(data), "w": img.width, "h": img.height,
                "filename": file.filename, "note": note}

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
    assert client.get("/plain").json() == {"ok": True}, "request ที่ไม่ใช่ multipart ต้องผ่านเฉยๆ"


def test_decorator():
    app = FastAPI()

    @app.post("/upload")
    @CompressUpload(quality=75)
    async def upload(file: UploadFile = File(...)):
        img = Image.open(file)
        return {"w": img.width, "h": img.height}

    client = TestClient(app)
    r = client.post("/upload", files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["w"] <= 1920


if __name__ == "__main__":
    test_middleware()
    test_decorator()
    print("ok")
