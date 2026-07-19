from .config import DEFAULT_CONFIG
from .core import compress

__all__ = ["compress", "DEFAULT_CONFIG"]

try:
    from .adapters.fastapi import CompressUpload, ImgCompress

    __all__ += ["CompressUpload", "ImgCompress"]
except ImportError:
    pass  # starlette/python-multipart ไม่ได้ติดตั้ง — ใช้ function mode ได้ปกติ
