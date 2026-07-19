# ImgCompress — Spec

```txt
ไลบรารี Python ที่ compress ภาพอัตโนมัติ ก่อนเข้า database/storage
โดยใช้โค้ดน้อยที่สุด — Framework-agnostic, drop-in, zero boilerplate
```

## แก่นของไลบรารี

ImgCompress มี 3 โหมดให้เลือกใช้ แล้วแต่ชอบ:

| โหมด | ใช้ยังไง | เหมาะกับ |
|:--|:--|:--|
| **Function** | `compressed = compress(file)` | เรียกใช้ตรงไหนก็ได้ |
| **Decorator** | `@CompressUpload()` แปะบน route | FastAPI route |
| **Middleware** | `app.add_middleware(ImgCompress)` | จัดการทุก request อัตโนมัติ |

ทุกโหมด工作了เหมือนกัน: **รับรูปมา → บีบอัด → ค่อยให้ handler จัดการต่อ**

## พฤติกรรมหลัก

1. รับ image file (UploadFile, bytes, Path, str)
2. ตรวจ format (JPEG/PNG/WebP เท่านั้น)
3. resize ถ้ากว้าง/สูงเกิน max
4. compress ด้วย quality ที่ตั้ง
5. คืน bytes ที่ compress แล้ว
6. ถ้าขนาดหลังจาก compress > ก่อน compress → คืนของเดิม (ไม่ทำให้ใหญ่ขึ้น)

## Zero dependency

- 依赖 Pillow ตัวเดียว
- ไม่มี dependency อื่น
- Python 3.10+

## Config defaults

```python
defaults = {
    "quality": 75,
    "max_width": 1920,
    "max_height": 1080,
    "fmt": "jpeg",        # jpeg | webp | png | auto (keep original)
    "strip_metadata": True,
    "min_file_size": 0,   # bytes — ข้ามไฟล์ที่เล็กกว่านี้
}
```

## Public API

```python
# --------------------------------------------------
# 1. Function mode
# --------------------------------------------------
compress(file, *, quality=75, max_width=1920, max_height=1080, fmt="jpeg")
    -> bytes
# รับ: UploadFile | bytes | str | Path
# คืน: bytes ที่ compress แล้ว

# --------------------------------------------------
# 2. Decorator mode (FastAPI)
# --------------------------------------------------
@CompressUpload(quality=75, max_width=1920)
async def handler(file: UploadFile):
    # file กลายเป็น BytesIO ที่ถูก compress แล้ว
    db.save(file)

# --------------------------------------------------
# 3. Middleware mode (FastAPI)
# --------------------------------------------------
from imgcompress import ImgCompress
app.add_middleware(ImgCompress, quality=75)
# แก้ไข request body ที่มีรูป → compress → ส่งต่อให้ route
```

## ข้อควรระวัง (spec)

- Middleware mode อาจเพิ่ม latency ~50ms ต่อ request ถ้าไฟล์ใหญ่
- ควร compress แบบ async ถ้าต้องการ performance สูง (future)
- ไลบรารีนี้ไม่จัดการ storage — compress เสร็จ user เอาไปทำอะไรต่อเอง

## โครงสร้างไฟล์ (เสนอ)

```
imgcompress/
├── __init__.py          # public API: 3 โหมด
├── core.py              # Pillow logic หลัก
├── config.py            # default config
└── adapters/
    ├── fastapi.py       # middleware + decorator สำหรับ FastAPI
    ├── flask.py         # middleware + decorator สำหรับ Flask
    └── django.py        # integration สำหรับ Django
```
