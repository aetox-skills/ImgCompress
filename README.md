# ImgCompress

บีบอัดรูปอัตโนมัติก่อนเข้า database/storage — โค้ดน้อยสุด, framework-agnostic, dependency ตัวเดียว (Pillow)

```bash
pip install imgcompress            # function mode (Pillow อย่างเดียว)
pip install imgcompress[fastapi]   # + decorator/middleware สำหรับ FastAPI
```

Python 3.10+

## ใช้งาน 3 โหมด

### 1. Function — เรียกตรงไหนก็ได้ (Flask, Django, Celery, script)

```python
from imgcompress import compress

compressed: bytes = compress(file)  # รับ UploadFile | bytes | str | Path | file-like
db.save(compressed)
```

### 2. Decorator — คุมเป็นราย route (FastAPI)

```python
from imgcompress import CompressUpload

@app.post("/upload")
@CompressUpload(quality=75, max_width=1920)
async def handler(file: UploadFile = File(...)):
    # file กลายเป็น BytesIO ที่ compress แล้ว (รองรับ list[UploadFile] ด้วย)
    db.save(file.read())
```

### 3. Middleware — จัดการทุก request ไม่ต้องแตะ route (FastAPI)

```python
from imgcompress import ImgCompress

app.add_middleware(ImgCompress, quality=75)
# ทุก multipart request ที่มีรูป → compress ก่อนถึง route อัตโนมัติ
```

## Options (ทุกโหมดใช้ชุดเดียวกัน)

| option | default | ความหมาย |
|:--|:--|:--|
| `quality` | `75` | คุณภาพ JPEG/WebP (1-100) |
| `max_width` | `1920` | กว้างเกินนี้ → resize (รักษา aspect ratio) |
| `max_height` | `1080` | สูงเกินนี้ → resize |
| `fmt` | `"jpeg"` | format ปลายทาง: `jpeg` \| `webp` \| `png` \| `auto` (คงของเดิม) |
| `strip_metadata` | `True` | ลบ EXIF (หลัง apply orientation แล้ว) |
| `min_file_size` | `0` | ไฟล์เล็กกว่านี้ (bytes) → ข้าม ไม่บีบ |

## สิ่งที่จัดการให้ (ที่เขียนเองแล้วมักพลาด)

- **ไม่มีทางได้ไฟล์ใหญ่ขึ้น** — ถ้าบีบแล้วใหญ่กว่าเดิม คืนไฟล์เดิม
- **EXIF orientation** — รูปมือถือแนวตั้งถูกหมุนให้ถูกด้านก่อน strip metadata (ไม่งั้นรูปเอียง)
- **โปร่งใส → JPEG** — composite ลงพื้นขาว ไม่ใช่สีขยะใต้ alpha channel
- **Animated GIF/WebP** — คืนไฟล์เดิม ไม่ทำ animation หายเงียบๆ
- **ไฟล์เสีย / ไม่ใช่รูป / format อื่น** — คืนไฟล์เดิม ไม่ crash (บีบเฉพาะ JPEG/PNG/WebP)
- **Decompression bomb** — ภาพเกิน ~89M pixel ถูกปฏิเสธโดย Pillow → คืนไฟล์เดิม
- ตรวจ format จากเนื้อไฟล์จริง ไม่เชื่อ extension/Content-Type

## ขอบเขต

- ไม่จัดการ storage — compress เสร็จได้ `bytes` ไปทำต่อเอง
- HEIC (iPhone) เปิดไม่ได้ → passthrough (ถ้าต้องการ ติดตั้ง `pillow-heif` แล้วแจ้ง issue)
- Compress เป็น sync — traffic สูงมากควร offload ไป thread pool เอง

## ทดสอบ

```bash
python test_core.py      # core logic
python test_fastapi.py   # integration กับ FastAPI จริง
```
