import os
import logging
from typing import List, Optional
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap
from database import ImageDatabase

logger = logging.getLogger(__name__)

class ThumbnailLoader(QThread):
    """后台加载缩略图，避免界面卡顿"""
    thumbnail_ready = pyqtSignal(int, QPixmap)  # item索引, 缩略图

    def __init__(self, image_paths: List[str], size: QSize = QSize(120, 120)):
        super().__init__()
        self.image_paths = image_paths
        self.size = size
        self._stop_flag = False

    def run(self):
        for idx, path in enumerate(self.image_paths):
            if self._stop_flag:
                break
            if not os.path.exists(path):
                continue
            pix = QPixmap(path)
            if not pix.isNull():
                scaled = pix.scaled(self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_ready.emit(idx, scaled)
            self.msleep(10)

    def stop(self):
        self._stop_flag = True


class SearchWorker(QThread):
    """后台执行数据库查询，返回结果和总数"""
    finished = pyqtSignal(list, int)

    def __init__(self, db: ImageDatabase, search_term: str = "",
                 category: Optional[str] = None, favorite: Optional[bool] = None,
                 private: Optional[bool] = None,
                 limit: int = 1000, offset: int = 0):
        super().__init__()
        self.db = db
        self.search_term = search_term
        self.category = category
        self.favorite = favorite
        self.private = private
        self.limit = limit
        self.offset = offset

    def run(self):
        try:
            rows, total = self.db.search_images(
                self.search_term, self.category, self.favorite,
                self.private, self.limit, self.offset
            )
            self.finished.emit(rows, total)
        except Exception as e:
            logger.exception("数据库查询失败")
            self.finished.emit([], 0)