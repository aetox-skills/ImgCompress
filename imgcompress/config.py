DEFAULT_CONFIG = {
    "quality": 75,
    "max_width": 1920,
    "max_height": 1080,
    "fmt": "jpeg",       # jpeg | webp | png | auto (keep original)
    "strip_metadata": True,
    "min_file_size": 0,  # bytes — ข้ามไฟล์ที่เล็กกว่านี้
    "max_file_size": 0,  # bytes — ข้ามไฟล์ที่ใหญ่กว่านี้ (0 = ไม่จำกัด), กันเปลือง CPU ถอดรหัสไฟล์มหึมา
}
