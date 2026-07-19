from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from .config import DEFAULT_CONFIG

try:
    import pillow_heif

    pillow_heif.register_heif_opener()  # เปิด HEIC/HEIF (iPhone) ได้ถ้าติดตั้ง pillow-heif
except ImportError:
    pass

_SAVE_FORMAT = {"jpeg": "JPEG", "webp": "WEBP", "png": "PNG"}
# input format ที่ยอมรับ: 3 ตัวที่ compress ลงได้ดี + format เก่า/พิเศษที่ Pillow เปิดได้
# (BMP/TIFF ไม่มี lossless quality knob แต่ resize ก็ช่วยลดขนาดได้เยอะอยู่ดี)
_SUPPORTED = frozenset(_SAVE_FORMAT.values()) | {"BMP", "TIFF", "GIF", "HEIF"}


def _read_bytes(file) -> bytes:
    if isinstance(file, bytes):
        return file
    if isinstance(file, (str, Path)):
        return Path(file).read_bytes()
    if hasattr(file, "file"):  # UploadFile (fastapi/starlette)
        data = file.file.read()
        file.file.seek(0)
        return data
    if hasattr(file, "read"):  # any file-like object
        data = file.read()
        if hasattr(file, "seek"):
            file.seek(0)
        return data
    raise TypeError(f"Unsupported file type: {type(file)!r}")


def compress(
    file,
    *,
    quality: int = DEFAULT_CONFIG["quality"],
    max_width: int = DEFAULT_CONFIG["max_width"],
    max_height: int = DEFAULT_CONFIG["max_height"],
    fmt: str = DEFAULT_CONFIG["fmt"],
    strip_metadata: bool = DEFAULT_CONFIG["strip_metadata"],
    min_file_size: int = DEFAULT_CONFIG["min_file_size"],
    max_file_size: int = DEFAULT_CONFIG["max_file_size"],
) -> bytes:
    if fmt != "auto" and fmt not in _SAVE_FORMAT:
        raise ValueError(f"invalid fmt: {fmt!r}, must be one of: auto, {', '.join(_SAVE_FORMAT)}")

    original = _read_bytes(file)

    if len(original) < min_file_size:
        return original

    if max_file_size and len(original) > max_file_size:
        return original  # ใหญ่เกินไป ไม่คุ้มถอดรหัส — คืนของเดิม ไม่พยายามบีบ

    try:
        img = Image.open(BytesIO(original))
        img.load()
    except Exception:
        return original  # ไม่ใช่ภาพที่เปิดได้ → คืนของเดิม

    if img.format not in _SUPPORTED:
        return original  # ตรวจ format: บีบอัดแค่ JPEG/PNG/WebP

    if getattr(img, "is_animated", False):
        return original  # ponytail: animated → passthrough, ทำ animated re-encode เมื่อมี use case จริง

    src_format = img.format  # เก็บก่อน transpose เพราะ copy ที่ได้กลับมา .format เป็น None
    img = ImageOps.exif_transpose(img)  # apply orientation ก่อน strip exif ไม่งั้นรูปมือถือเอียง

    img.thumbnail((max_width, max_height))  # resize เฉพาะถ้าเกิน max, รักษา aspect ratio

    out_format = src_format if fmt == "auto" else _SAVE_FORMAT[fmt]

    if strip_metadata:
        img.info.pop("exif", None)  # ponytail: ลบเฉพาะ exif ไม่ใช่ icc/xmp ทั้งหมด, ขยายทีหลังถ้าจำเป็น

    if out_format == "JPEG" and img.mode != "RGB":
        if img.mode == "P":
            img = img.convert("RGBA")
        if "A" in img.mode:  # composite ลงพื้นขาว ไม่งั้นส่วนโปร่งใสโชว์สีขยะใต้ alpha
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        else:
            img = img.convert("RGB")

    if out_format == "JPEG":
        save_kwargs = {"quality": quality, "optimize": True}
    elif out_format == "WEBP":
        save_kwargs = {"quality": quality}
    elif out_format == "PNG":
        save_kwargs = {"optimize": True}
    else:  # BMP/TIFF/GIF/HEIF ตอน fmt="auto" — ไม่มี quality knob, ปล่อยให้ resize ทำงานอย่างเดียว
        save_kwargs = {}

    buf = BytesIO()
    img.save(buf, format=out_format, **save_kwargs)
    compressed = buf.getvalue()

    return compressed if len(compressed) < len(original) else original
