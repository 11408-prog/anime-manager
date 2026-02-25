import os
import shutil
import logging
from typing import List, Optional

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QListWidget, QListWidgetItem,
                             QMessageBox, QMenu, QAbstractItemView, QSplitter,
                             QDialog, QFileDialog)
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QThread, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QDesktopServices

from database import ImageDatabase
from workers import ThumbnailLoader, SearchWorker
from dialogs import EditImageDialog

logger = logging.getLogger(__name__)

class PrivateSpaceWindow(QMainWindow):
    def __init__(self, db: ImageDatabase, images_dir: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.images_dir = images_dir
        self.setWindowTitle("私密空间")
        self.setGeometry(200, 200, 1000, 600)

        # 控件
        self.list_widget = QListWidget()
        self.image_label = QLabel("点击图片预览")
        self.current_filename = None
        self.current_pixmap = None
        self.current_image_infos = []  # 存储当前显示的图片信息
        self.thumb_loader = None
        self.search_worker = None

        self.init_ui()
        self.load_private_images()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 工具栏
        toolbar = QHBoxLayout()
        back_btn = QPushButton("返回主界面")
        back_btn.clicked.connect(self.close)
        toolbar.addWidget(back_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_private_images)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 主分割区域
        splitter = QSplitter(Qt.Horizontal)

        # 左侧图片网格
        self.list_widget.setViewMode(QListWidget.IconMode)
        self.list_widget.setIconSize(QSize(120, 120))
        self.list_widget.setGridSize(QSize(150, 180))
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemClicked.connect(self.on_item_click)
        self.list_widget.itemDoubleClicked.connect(self.edit_image)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        splitter.addWidget(self.list_widget)

        # 右侧预览区
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #f9f9f9; border:1px solid #ddd; border-radius:8px;")
        self.image_label.mouseDoubleClickEvent = self.on_image_double_click
        right_layout.addWidget(self.image_label)

        btn_layout = QHBoxLayout()
        fullscreen_btn = QPushButton("全屏查看")
        fullscreen_btn.clicked.connect(self.show_fullscreen)
        btn_layout.addWidget(fullscreen_btn)

        download_btn = QPushButton("下载图片")
        download_btn.clicked.connect(self.download_image)
        btn_layout.addWidget(download_btn)

        right_layout.addLayout(btn_layout)
        splitter.addWidget(right)
        splitter.setSizes([700, 400])

        layout.addWidget(splitter)

        self.statusBar().showMessage("就绪")

    def load_private_images(self):
        """加载所有私密图片"""
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.quit()
            self.search_worker.wait()

        self.search_worker = SearchWorker(self.db, private=True)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.start()
        self.statusBar().showMessage("正在加载私密图片...")

    def on_search_finished(self, rows, total):
        self.current_image_infos = rows
        self.list_widget.clear()
        if not rows:
            self.statusBar().showMessage("私密空间暂无图片")
            return

        for idx, (filename, disp, cat, tags, fav, _) in enumerate(rows):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, filename)
            item.setData(Qt.UserRole+1, disp)
            item.setData(Qt.UserRole+2, cat)
            item.setData(Qt.UserRole+3, tags)
            item.setData(Qt.UserRole+4, fav)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setText(" 加载中...")
            self.list_widget.addItem(item)

        self.statusBar().showMessage(f"私密空间共 {total} 张图片")
        self.start_thumbnail_loading()

    def start_thumbnail_loading(self):
        if self.thumb_loader and self.thumb_loader.isRunning():
            self.thumb_loader.stop()
            self.thumb_loader.wait()

        image_paths = [os.path.join(self.images_dir, info[0]) for info in self.current_image_infos]
        self.thumb_loader = ThumbnailLoader(image_paths, QSize(120, 120))
        self.thumb_loader.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_loader.start()

    def on_thumbnail_ready(self, idx: int, pixmap: QPixmap):
        if idx >= self.list_widget.count():
            return
        item = self.list_widget.item(idx)
        if not item:
            return
        filename, disp, cat, tags, fav, _ = self.current_image_infos[idx]
        fav_mark = "❤️ " if fav else ""
        item.setText(f"{fav_mark}{disp}\n[{cat}] {tags}")
        item.setIcon(QIcon(pixmap))

    def on_item_click(self, item):
        self.current_filename = item.data(Qt.UserRole)
        path = os.path.join(self.images_dir, self.current_filename)
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                size = self.image_label.size()
                scaled = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
                self.current_pixmap = pix
        fav = item.data(Qt.UserRole+4) or 0
        self.statusBar().showMessage(f"标签: {item.data(Qt.UserRole+3)}", 3000)

    def edit_image(self, item):
        fn = item.data(Qt.UserRole)
        old_cat = item.data(Qt.UserRole+2) or ""
        old_tags = item.data(Qt.UserRole+3) or ""
        dlg = EditImageDialog(old_cat, old_tags, self, self.db)
        if dlg.exec_() == QDialog.Accepted:
            new_cat, new_tags = dlg.get_values()
            try:
                self.db.update_image(fn, new_cat, new_tags)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"更新失败: {e}")
                return
            item.setData(Qt.UserRole+2, new_cat)
            item.setData(Qt.UserRole+3, new_tags)
            fav = item.data(Qt.UserRole+4) or 0
            fav_mark = "❤️ " if fav else ""
            disp = item.data(Qt.UserRole+1)
            item.setText(f"{fav_mark}{disp}\n[{new_cat}] {new_tags}")
            self.statusBar().showMessage("更新成功", 2000)

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")
        remove_private_action = menu.addAction("移出私密空间")
        action = menu.exec_(self.list_widget.mapToGlobal(pos))
        if action == edit_action:
            self.edit_image(item)
        elif action == delete_action:
            self.delete_single(item)
        elif action == remove_private_action:
            self.remove_from_private(item)

    def delete_single(self, item):
        fn = item.data(Qt.UserRole)
        path = os.path.join(self.images_dir, fn)
        reply = QMessageBox.question(self, "确认删除", f"确定删除图片 {fn} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
            self.db.delete_image(fn)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除失败: {e}")
            return
        self.statusBar().showMessage(f"已删除 {fn}")
        self.load_private_images()

    def remove_from_private(self, item):
        """将图片移出私密空间（变为普通图片）"""
        fn = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "移出私密空间",
                                     f"确定将图片 '{fn}' 移出私密空间吗？\n移出后将在主界面显示。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return
        try:
            self.db.set_private(fn, False)
            self.statusBar().showMessage(f"已移出私密空间: {fn}")
            self.load_private_images()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"操作失败: {e}")

    def show_fullscreen(self):
        if not self.current_filename:
            QMessageBox.information(self, "提示", "请先单击选择图片")
            return
        path = os.path.join(self.images_dir, self.current_filename)
        if not os.path.exists(path):
            QMessageBox.critical(self, "错误", "图片文件不存在")
            return
        try:
            os.startfile(path)
        except AttributeError:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_image_double_click(self, event):
        self.show_fullscreen()

    def download_image(self):
        if not self.current_filename:
            QMessageBox.information(self, "提示", "请先单击选择图片")
            return
        src = os.path.join(self.images_dir, self.current_filename)
        if not os.path.exists(src):
            QMessageBox.critical(self, "错误", "图片文件不存在")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "保存图片", self.current_filename,
                "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if dest:
            try:
                shutil.copy2(src, dest)
                QMessageBox.information(self, "成功", "图片已保存")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {e}")