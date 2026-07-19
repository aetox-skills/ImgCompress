"""Self-check: python test_core.py"""
from io import BytesIO

from PIL import Image

from imgcompress import compress


def _make_jpeg(w=3000, h=2000) -> bytes:
    img = Image.new("RGB", (w, h), color=(200, 100, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_resizes_and_shrinks():
    original = _make_jpeg()
    out = compress(original, max_width=1920, max_height=1080, quality=75)
    assert len(out) < len(original)
    resized = Image.open(BytesIO(out))
    assert resized.width <= 1920 and resized.height <= 1080


def test_never_grows():
    tiny = _make_jpeg(50, 50)
    out = compress(tiny, quality=100)
    assert len(out) <= len(tiny)


def test_unsupported_format_passthrough():
    data = b"not an image"
    assert compress(data) == data


def test_min_file_size_skips():
    original = _make_jpeg()
    out = compress(original, min_file_size=10**9)
    assert out == original


def test_exif_orientation_applied():
    img = Image.new("RGB", (200, 100), (255, 0, 0))
    exif = Image.Exif()
    exif[274] = 6  # rotate 270 — เคสรูปมือถือแนวตั้ง
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95, exif=exif)
    out = compress(buf.getvalue(), quality=75)
    out_img = Image.open(BytesIO(out))
    assert out_img.size == (100, 200), "pixel ต้องถูกหมุนตาม orientation tag"
    assert out_img.getexif().get(274) is None


def test_rgba_composites_white():
    import random

    random.seed(1)
    rgba = Image.new("RGBA", (100, 100))
    px = rgba.load()
    for x in range(100):
        for y in range(100):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), 0, 0)
    buf = BytesIO()
    rgba.save(buf, format="PNG")
    out = compress(buf.getvalue(), fmt="jpeg", quality=90)
    r, g, b = Image.open(BytesIO(out)).getpixel((50, 50))
    assert min(r, g, b) > 230, f"ส่วนโปร่งใสต้องเป็นพื้นขาว ไม่ใช่สีขยะ: {(r, g, b)}"


def test_animated_passthrough():
    frames = [Image.new("RGB", (50, 50), c) for c in [(255, 0, 0), (0, 0, 255)]]
    buf = BytesIO()
    frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0)
    original = buf.getvalue()
    assert compress(original, fmt="auto") == original


def test_decorator_list_uploadfile():
    import asyncio

    from starlette.datastructures import UploadFile

    from imgcompress import CompressUpload

    @CompressUpload(quality=75)
    async def handler(files):
        return files

    uploads = [UploadFile(BytesIO(_make_jpeg()), filename=f"{i}.jpg") for i in range(2)]
    result = asyncio.run(handler(files=uploads))
    assert all(isinstance(f, BytesIO) for f in result)
    assert all(Image.open(f).width <= 1920 for f in result)


if __name__ == "__main__":
    test_resizes_and_shrinks()
    test_never_grows()
    test_unsupported_format_passthrough()
    test_min_file_size_skips()
    test_exif_orientation_applied()
    test_rgba_composites_white()
    test_animated_passthrough()
    test_decorator_list_uploadfile()
    print("ok")
