import logging
import imagehash
from PIL import Image, UnidentifiedImageError
from typing import Optional

logger = logging.getLogger(__name__)

def calculate_phash(filepath: str) -> Optional[str]:
    """计算图片感知哈希，失败时返回 None"""
    try:
        with Image.open(filepath) as img:
            return str(imagehash.phash(img))
    except FileNotFoundError:
        logger.error("文件不存在: %s", filepath)
    except UnidentifiedImageError:
        logger.error("无法识别的图片格式: %s", filepath)
    except Exception as e:
        logger.exception("计算 pHASH 时发生未知错误: %s - %s", filepath, e)
    return None