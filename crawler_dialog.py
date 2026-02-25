import os
import sys
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QListWidget, QListWidgetItem,
                             QProgressBar, QMessageBox, QApplication, QCheckBox,
                             QScrollArea, QGridLayout, QFrame, QSizePolicy, QWidget)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon

from crawler import BilibiliCrawler


class CrawlWorker(QThread):
    """后台下载线程"""
    progress = pyqtSignal(int, int, str)   # current, total, filename
    finished = pyqtSignal(list)             # 成功下载的文件路径列表

    def __init__(self, crawler, selected_indices):
        super().__init__()
        self.crawler = crawler
        self.selected_indices = selected_indices

    def run(self):
        self.crawler.callback = self.on_progress
        downloaded = self.crawler.download_images(self.selected_indices)
        self.finished.emit(downloaded)

    def on_progress(self, current, total, filename):
        self.progress.emit(current, total, filename)

    def stop(self):
        self.crawler.stop()


class DownloadPreviewDialog(QDialog):
    """下载完成后预览图片并选择要保留的图片"""
    def __init__(self, downloaded_files: list, parent=None):
        super().__init__(parent)
        self.downloaded_files = downloaded_files  # 文件路径列表
        self.selected_files = []                  # 用户最终选择的文件
        self.checkboxes = []                       # 存储复选框以获取状态
        self.setWindowTitle("预览下载的图片")
        self.setMinimumSize(700, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 说明标签
        info_label = QLabel(f"已下载 {len(self.downloaded_files)} 张图片，请勾选要保留的图片（未勾选的将被删除）:")
        layout.addWidget(info_label)

        # 滚动区域用于显示图片网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setSpacing(10)

        # 为每个下载的图片创建缩略图和复选框
        cols = 3  # 每行3个
        for idx, filepath in enumerate(self.downloaded_files):
            # 创建包含图片和复选框的容器
            frame = QFrame()
            frame.setFrameShape(QFrame.Box)
            frame.setLineWidth(1)
            frame_layout = QVBoxLayout(frame)

            # 缩略图
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                # 缩放图片到合适大小
                pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label = QLabel()
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignCenter)
                frame_layout.addWidget(label)
            else:
                label = QLabel("无法加载")
                label.setAlignment(Qt.AlignCenter)
                frame_layout.addWidget(label)

            # 文件名（简短）
            filename = os.path.basename(filepath)
            name_label = QLabel(filename[:20] + ("..." if len(filename) > 20 else ""))
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setToolTip(filename)  # 完整文件名作为提示
            frame_layout.addWidget(name_label)

            # 复选框
            checkbox = QCheckBox("保留")
            checkbox.setChecked(True)  # 默认全部保留
            checkbox.stateChanged.connect(self.update_selection)
            frame_layout.addWidget(checkbox)

            # 存储复选框以便后续获取状态
            self.checkboxes.append((filepath, checkbox))

            # 添加到网格
            grid.addWidget(frame, idx // cols, idx % cols)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        btn_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_layout.addWidget(self.deselect_all_btn)

        btn_layout.addStretch()

        self.ok_btn = QPushButton("确认导入")
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def select_all(self):
        for _, cb in self.checkboxes:
            cb.setChecked(True)

    def deselect_all(self):
        for _, cb in self.checkboxes:
            cb.setChecked(False)

    def update_selection(self):
        """更新选择状态（实时更新，但不做删除）"""
        pass

    def get_selected_files(self):
        """返回用户勾选的文件路径列表"""
        selected = []
        for filepath, cb in self.checkboxes:
            if cb.isChecked():
                selected.append(filepath)
        return selected

    def accept(self):
        """确认后，删除未选中的文件，并返回选中的文件"""
        self.selected_files = self.get_selected_files()
        # 删除未选中的文件
        for filepath, cb in self.checkboxes:
            if not cb.isChecked() and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"删除文件失败 {filepath}: {e}")
        super().accept()


class BilibiliCrawlerDialog(QDialog):
    """B站图片爬取对话框（专门针对B站）"""

    def __init__(self, download_folder, parent=None):
        super().__init__(parent)
        self.download_folder = download_folder
        self.crawler = None
        self.worker = None
        self.image_urls = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("B站图片爬取")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout()

        # URL输入行
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("B站页面URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("例如: https://www.bilibili.com/read/cv123456 或 /opus/xxx")
        url_layout.addWidget(self.url_edit)
        self.fetch_btn = QPushButton("获取图片")
        self.fetch_btn.clicked.connect(self.fetch_images)
        url_layout.addWidget(self.fetch_btn)
        layout.addLayout(url_layout)

        # 图片列表（带复选框）
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(QLabel("选择要下载的图片:"))
        layout.addWidget(self.list_widget)

        # 全选/取消
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.deselect_all_btn)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        # 统一标签输入
        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("统一标签（可选）:"))
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("多个用逗号分隔，将应用于所有下载的图片")
        tag_layout.addWidget(self.tag_edit)
        layout.addLayout(tag_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 下载按钮
        self.download_btn = QPushButton("下载选中图片")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        layout.addWidget(self.download_btn)

        # 停止按钮
        self.stop_btn = QPushButton("停止下载")
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setVisible(False)
        layout.addWidget(self.stop_btn)

        self.setLayout(layout)

    def fetch_images(self):
        """获取页面中的图片URL"""
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "请输入B站页面URL")
            return

        self.fetch_btn.setEnabled(False)
        self.list_widget.clear()
        self.image_urls = []
        self.download_btn.setEnabled(False)

        class FetchThread(QThread):
            urls_fetched = pyqtSignal(list)
            error = pyqtSignal(str)

            def __init__(self, url, download_folder):
                super().__init__()
                self.url = url
                self.download_folder = download_folder

            def run(self):
                try:
                    crawler = BilibiliCrawler(self.url, self.download_folder)
                    urls = crawler.fetch_image_urls()
                    self.crawler = crawler
                    self.urls_fetched.emit(urls)
                except Exception as e:
                    self.error.emit(str(e))

        self.fetch_thread = FetchThread(url, self.download_folder)
        self.fetch_thread.urls_fetched.connect(self.on_urls_fetched)
        self.fetch_thread.error.connect(lambda e: QMessageBox.critical(self, "错误", f"爬取失败: {e}"))
        self.fetch_thread.finished.connect(lambda: self.fetch_btn.setEnabled(True))
        self.fetch_thread.start()

    def on_urls_fetched(self, urls):
        self.image_urls = urls
        for url in urls:
            item = QListWidgetItem(url)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

        if urls:
            self.download_btn.setEnabled(True)
            QMessageBox.information(self, "完成", f"找到 {len(urls)} 张图片，请选择要下载的")
        else:
            QMessageBox.information(self, "提示", "未找到图片，可能是页面无图或结构更新")

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)

    def start_download(self):
        """开始下载选中的图片"""
        selected = []
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).checkState() == Qt.Checked:
                selected.append(i)

        if not selected:
            QMessageBox.information(self, "提示", "请至少选择一张图片")
            return

        # 创建新的爬虫实例
        self.crawler = BilibiliCrawler(self.url_edit.text().strip(), self.download_folder)
        self.crawler.image_urls = self.image_urls

        self.worker = CrawlWorker(self.crawler, selected)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.start()

        self.download_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(selected))

    def update_progress(self, current, total, filename):
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"下载中 {current}/{total} - {filename}")

    def on_download_finished(self, downloaded_files):
        """下载完成后，弹出预览对话框让用户选择"""
        self.stop_btn.setVisible(False)
        self.download_btn.setVisible(True)
        self.progress_bar.setVisible(False)

        if not downloaded_files:
            QMessageBox.warning(self, "提示", "没有图片被下载")
            return

        # 弹出预览对话框
        preview_dlg = DownloadPreviewDialog(downloaded_files, self)
        if preview_dlg.exec_() == QDialog.Accepted:
            selected_files = preview_dlg.selected_files
            if selected_files:
                common_tags = self.tag_edit.text().strip()
                parent = self.parent()
                if parent and hasattr(parent, 'db'):
                    imported = 0
                    for filepath in selected_files:
                        filename = os.path.basename(filepath)
                        display_name = filename
                        category = ""
                        tags = common_tags
                        try:
                            parent.db.add_image(filename, display_name, category, tags)
                            imported += 1
                        except Exception as e:
                            print(f"添加到数据库失败: {e}")
                    # 刷新主界面
                    parent.filter_images()
                    QMessageBox.information(self, "完成", f"成功导入 {imported} 张图片到图库")
                else:
                    QMessageBox.information(self, "完成", f"下载完成，共 {len(selected_files)} 张图片")
            else:
                # 用户没有勾选任何图片（但理论上不会，因为可以取消）
                QMessageBox.information(self, "提示", "未选择任何图片，所有下载的图片已被删除")
        else:
            # 用户取消了预览，删除所有下载的文件
            for filepath in downloaded_files:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
            QMessageBox.information(self, "提示", "已取消导入，下载的图片已删除")

    def stop_download(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)