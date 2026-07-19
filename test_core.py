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


def test_max_file_size_skips_decode():
    original = _make_jpeg()
    out = compress(original, max_file_size=10)  # ไฟล์จริงใหญ่กว่านี้แน่ๆ
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


def _make_noisy(fmt, w=1500, h=1000, **save_kw) -> bytes:
    import random

    random.seed(9)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    buf = BytesIO()
    img.save(buf, format=fmt, **save_kw)
    return buf.getvalue()


def test_bmp_and_tiff_convert_to_jpeg():
    for fmt in ("BMP", "TIFF"):
        original = _make_noisy(fmt)
        out = compress(original, quality=75)
        out_img = Image.open(BytesIO(out))
        assert len(out) < len(original), f"{fmt} ควรเล็กลงมากหลังแปลงเป็น JPEG"
        assert out_img.format == "JPEG"


def test_gif_static_supported():
    original = _make_noisy("GIF")
    out = compress(original, quality=75)
    assert Image.open(BytesIO(out)).format == "JPEG"
    assert len(out) < len(original)


def test_heic_supported_if_plugin_installed():
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        return  # pillow-heif เป็น optional extra — ข้ามถ้าไม่ได้ติดตั้ง

    original = _make_noisy("HEIF", quality=95)
    out = compress(original, quality=75)
    out_img = Image.open(BytesIO(out))
    assert out_img.format == "JPEG"
    assert out_img.width <= 1920


def test_decorator_list_uploadfile():
    import asyncio

    from starlette.datastructures import UploadFile

    from imgcompress import CompressUpload

    @CompressUpload(quality=75)
    async def handler(files):
        return files

    uploads = [UploadFile(BytesIO(_make_jpeg()), filename=f"{i}.jpg") for i in range(2)]
    result = asyncio.run(handler(files=uploads))
    assert all(isinstance(f, UploadFile) for f in result), "ต้องยังเป็น UploadFile รักษา contract เดิม"

    async def _check():
        for f in result:
            data = await f.read()
            assert Image.open(BytesIO(data)).width <= 1920

    asyncio.run(_check())


if __name__ == "__main__":
    test_resizes_and_shrinks()
    test_never_grows()
    test_unsupported_format_passthrough()
    test_min_file_size_skips()
    test_max_file_size_skips_decode()
    test_exif_orientation_applied()
    test_rgba_composites_white()
    test_animated_passthrough()
    test_bmp_and_tiff_convert_to_jpeg()
    test_gif_static_supported()
    test_heic_supported_if_plugin_installed()
    test_decorator_list_uploadfile()
    print("ok")
