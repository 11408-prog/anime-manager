import os
import shutil
import random
import datetime
import json
import zipfile
import tempfile
import logging
import sys
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QFileDialog, QInputDialog, QMessageBox, QComboBox, QCompleter,
    QAbstractItemView, QSplitter, QDialog, QShortcut, QMenu, QProgressBar,
    QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt, QSize, QUrl, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QKeySequence, QDesktopServices

from database import ImageDatabase, DuplicateImageError
from dialogs import EditImageDialog, TagSuggestDialog, TagCloudDialog
from utils import calculate_phash
import ui
from workers import ThumbnailLoader, SearchWorker
from crawler_dialog import BilibiliCrawlerDialog as CrawlerDialog
from password_dialog import PasswordDialog
from private_window import PrivateSpaceWindow
import password

logger = logging.getLogger(__name__)

# 添加图片对话框
class AddImageDialog(QDialog):
    def __init__(self, db: ImageDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("添加图片信息")
        self.setModal(True)
        self.resize(300, 200)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("可留空")
        form_layout.addRow("分类:", self.category_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("例如: 可爱, 初音未来")
        form_layout.addRow("标签 (逗号分隔):", self.tags_edit)
        layout.addLayout(form_layout)

        # 私密选项
        self.private_check = QPushButton("设为私密")
        self.private_check.setCheckable(True)
        layout.addWidget(self.private_check)

        if self.db:
            all_tags = self.db.get_all_tags()
            completer = QCompleter(all_tags, self)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.tags_edit.setCompleter(completer)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        self.tags_edit.setFocus()

    def get_values(self) -> Tuple[str, str, bool]:
        return (self.category_edit.text().strip(),
                self.tags_edit.text().strip(),
                self.private_check.isChecked())

# 主窗口类
class ImageApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("二次元图片收藏")
        self.setGeometry(100, 100, 1200, 800)

        # 修正：判断是否为打包后的环境，使用 exe 所在目录作为基础路径
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(__file__)

        self.data_dir = os.path.join(base_dir, "data")
        self.images_dir = os.path.join(self.data_dir, "images")
        self.thumb_dir = os.path.join(self.data_dir, "thumbnails")
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.thumb_dir, exist_ok=True)

        self.db = ImageDatabase(os.path.join(self.data_dir, "images.db"))

        self.current_pixmap = None
        self.current_filename = None
        self.current_item_index = -1
        self.dark_mode = False

        self.thumb_loader = None
        self.search_worker = None
        self.current_image_infos = []  # 每个元素为 (filename, display_name, category, tags_str, favorite, is_private)

        # 从 ui 模块获取样式
        self.light_style = ui.LIGHT_STYLE
        self.dark_style = ui.DARK_STYLE

        self.init_ui()
        self.apply_styles(self.light_style)
        self.setup_shortcuts()
        self.refresh_all()

    def apply_styles(self, style):
        self.setStyleSheet(style)

    def toggle_theme(self, checked):
        if checked:
            self.apply_styles(self.dark_style)
            self.theme_btn.setText("☀️ 浅色模式")
        else:
            self.apply_styles(self.light_style)
            self.theme_btn.setText("🌙 深色模式")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addLayout(ui.create_toolbar1(self))
        layout.addLayout(ui.create_toolbar2(self))
        layout.addWidget(ui.create_main_splitter(self), 1)

        self.statusBar().showMessage("就绪")

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_image)
        QShortcut(QKeySequence("Ctrl+F"), self, self.search_input.setFocus)
        QShortcut(QKeySequence("Ctrl+A"), self, self.select_all)
        QShortcut(QKeySequence("Delete"), self, self.batch_delete)
        QShortcut(QKeySequence("Ctrl+D"), self, self.deselect_all)

    def open_crawler(self):
        dlg = CrawlerDialog(self.images_dir, self)
        dlg.exec_()

    def open_private_space(self):
        """打开私密空间（需要密码验证）"""
        # 检查是否已设置密码
        if password.get_password_hash() is None:
            # 未设置，弹出设置密码对话框
            dlg = PasswordDialog('set', self)
            if dlg.exec_() != QDialog.Accepted:
                return
            # 设置成功后，再次验证（或直接进入）
            dlg = PasswordDialog('verify', self)
            if dlg.exec_() != QDialog.Accepted:
                return
        else:
            dlg = PasswordDialog('verify', self)
            if dlg.exec_() != QDialog.Accepted:
                return

        # 密码正确，打开私密空间窗口
        self.private_window = PrivateSpaceWindow(self.db, self.images_dir, self)
        self.private_window.show()

    def refresh_all(self):
        self.load_all_tags_async()
        self.load_categories_async()
        self.filter_images()

    def load_all_tags_async(self):
        class TagLoader(QThread):
            finished = pyqtSignal(list)
            def run(self):
                tags = self.parent.db.get_all_tags()
                self.finished.emit(tags)
        self.tag_loader = TagLoader()
        self.tag_loader.parent = self
        self.tag_loader.finished.connect(self._on_tags_loaded)
        self.tag_loader.start()

    def _on_tags_loaded(self, tags):
        completer = QCompleter(tags, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.search_input.setCompleter(completer)

    def load_categories_async(self):
        class CategoryLoader(QThread):
            finished = pyqtSignal(list)
            def run(self):
                cats = self.parent.db.get_all_categories()
                self.finished.emit(cats)
        self.cat_loader = CategoryLoader()
        self.cat_loader.parent = self
        self.cat_loader.finished.connect(self._on_categories_loaded)
        self.cat_loader.start()

    def _on_categories_loaded(self, cats):
        self.category_combo.clear()
        self.category_combo.addItem("全部", None)
        for c in cats:
            self.category_combo.addItem(c, c)

    def filter_images(self):
        cat = self.category_combo.currentData()
        text = self.search_input.text().strip()
        fav_val = self.fav_combo.currentData()  # None, 1, 0
        # 主界面默认不显示私密图片
        private = False

        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.quit()
            self.search_worker.wait()

        self.search_worker = SearchWorker(self.db, text, cat, fav_val, private=private)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.start()
        self.statusBar().showMessage("正在加载图片...")

    def on_search_finished(self, rows, total):
        """rows: 列表，每个元素为 (filename, display_name, category, tags_str, favorite, is_private)"""
        self.current_image_infos = rows
        self.list_widget.clear()
        if not rows:
            self.statusBar().showMessage("没有找到图片")
            return

        for idx, (filename, disp, cat, tags, fav, _) in enumerate(rows):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, filename)
            item.setData(Qt.UserRole+1, disp)
            item.setData(Qt.UserRole+2, cat)
            item.setData(Qt.UserRole+3, tags)
            item.setData(Qt.UserRole+4, fav)  # 普通收藏状态
            # 私密状态暂时不用（主界面已过滤）
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setText(" 加载中...")
            self.list_widget.addItem(item)

        self.statusBar().showMessage(f"共 {total} 张图片，已加载 {len(rows)} 张")
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
        self.current_item_index = self.list_widget.row(item)
        path = os.path.join(self.images_dir, self.current_filename)
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                size = self.image_label.size()
                scaled = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
                self.current_pixmap = pix
        fav = item.data(Qt.UserRole+4) or 0
        self.fav_btn.setChecked(bool(fav))
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
        similar_action = menu.addAction("查找相似")
        # 新增移入私密空间选项
        private_action = menu.addAction("🔒 移入私密空间")
        action = menu.exec_(self.list_widget.mapToGlobal(pos))
        if action == edit_action:
            self.edit_image(item)
        elif action == delete_action:
            self.delete_single(item)
        elif action == similar_action:
            self.current_filename = item.data(Qt.UserRole)
            self.find_similar_images()
        elif action == private_action:
            self.move_to_private(item)

    def move_to_private(self, item):
        """将图片移入私密空间"""
        fn = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "移入私密空间",
                                     f"确定将图片 '{fn}' 移入私密空间吗？\n移入后将在主界面隐藏，需密码查看。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return
        try:
            self.db.set_private(fn, True)
            self.statusBar().showMessage(f"已移入私密空间: {fn}")
            self.filter_images()  # 刷新主界面，图片消失
        except Exception as e:
            QMessageBox.critical(self, "错误", f"操作失败: {e}")

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
        self.filter_images()

    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "",
                "图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.webp)")
        if not path:
            return

        base = os.path.basename(path)
        name, ext = os.path.splitext(base)
        dest = base
        cnt = 1
        while os.path.exists(os.path.join(self.images_dir, dest)):
            dest = f"{name}_{cnt}{ext}"
            cnt += 1

        dest_path = os.path.join(self.images_dir, dest)
        try:
            shutil.copy2(path, dest_path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制失败: {e}")
            return

        phash = calculate_phash(dest_path)

        dlg = AddImageDialog(self.db, self)
        if dlg.exec_() != QDialog.Accepted:
            os.remove(dest_path)
            return
        cat, tags, is_private = dlg.get_values()

        try:
            self.db.add_image(dest, base, cat, tags, phash, is_private=is_private)
        except DuplicateImageError:
            QMessageBox.critical(self, "错误", "图片已存在")
            os.remove(dest_path)
            return
        except Exception as e:
            QMessageBox.critical(self, "错误", f"数据库错误: {e}")
            os.remove(dest_path)
            return

        self.statusBar().showMessage(f"已添加: {dest}")
        self.filter_images()

    def find_similar_images(self):
        if not self.current_filename:
            QMessageBox.information(self, "提示", "请先单击选择图片")
            return
        path = os.path.join(self.images_dir, self.current_filename)
        target_phash = calculate_phash(path)
        if not target_phash:
            QMessageBox.critical(self, "错误", "无法计算图片哈希")
            return

        class SimilarWorker(QThread):
            finished = pyqtSignal(list)
            def __init__(self, db, target_phash, current_fn):
                super().__init__()
                self.db = db
                self.target_phash = target_phash
                self.current_fn = current_fn

            def run(self):
                with self.db.get_connection() as conn:
                    rows = conn.execute("SELECT filename, phash FROM images WHERE phash IS NOT NULL").fetchall()
                similar = []
                threshold = 30
                for fn, ph in rows:
                    if ph and fn != self.current_fn:
                        try:
                            distance = bin(int(ph, 16) ^ int(self.target_phash, 16)).count('1')
                            if distance <= threshold:
                                similar.append(fn)
                        except:
                            continue
                self.finished.emit(similar)

        self.similar_worker = SimilarWorker(self.db, target_phash, self.current_filename)
        self.similar_worker.finished.connect(self._on_similar_found)
        self.similar_worker.start()
        self.statusBar().showMessage("正在查找相似图片...")

    def _on_similar_found(self, similar_files):
        if not similar_files:
            QMessageBox.information(self, "结果", "未找到相似图片")
            return
        self.load_images_by_filenames(similar_files)

    def load_images_by_filenames(self, filenames: List[str]):
        if not filenames:
            self.list_widget.clear()
            return
        placeholders = ','.join(['?' for _ in filenames])
        query = f"SELECT filename, display_name, category, tags, favorite FROM images WHERE filename IN ({placeholders})"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, filenames).fetchall()
        # 转换 rows 为 (filename, disp, cat, tags, fav) 元组
        self.current_image_infos = [(r[0], r[1], r[2], r[3], r[4], False) for r in rows]  # 假 is_private
        self.list_widget.clear()
        for idx, (fn, disp, cat, tags, fav, _) in enumerate(self.current_image_infos):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, fn)
            item.setData(Qt.UserRole+1, disp)
            item.setData(Qt.UserRole+2, cat)
            item.setData(Qt.UserRole+3, tags)
            item.setData(Qt.UserRole+4, fav)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setText(" 加载中...")
            self.list_widget.addItem(item)
        self.start_thumbnail_loading()
        self.statusBar().showMessage(f"找到 {len(rows)} 张相似图片")

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

    def batch_delete(self):
        checked = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item)
        if not checked:
            QMessageBox.information(self, "提示", "没有选中图片")
            return
        if QMessageBox.question(self, "确认删除",
                f"确定删除选中的 {len(checked)} 张图片？",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
            return

        for item in checked:
            fn = item.data(Qt.UserRole)
            path = os.path.join(self.images_dir, fn)
            if os.path.exists(path):
                os.remove(path)
            try:
                self.db.delete_image(fn)
            except Exception as e:
                logger.error("删除图片失败 %s: %s", fn, e)

        self.statusBar().showMessage(f"已删除 {len(checked)} 张图片")
        self.filter_images()

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)
        self.update_selection_status()

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)
        self.update_selection_status()

    def update_selection_status(self):
        selected = sum(1 for i in range(self.list_widget.count())
                       if self.list_widget.item(i).checkState() == Qt.Checked)
        total = self.list_widget.count()
        self.statusBar().showMessage(f"共 {total} 张图片，已选择 {selected} 张")

    def random_walk(self):
        count = self.list_widget.count()
        if count == 0:
            QMessageBox.information(self, "提示", "当前没有图片可随机")
            return
        index = random.randint(0, count - 1)
        item = self.list_widget.item(index)
        self.list_widget.setCurrentItem(item)
        self.on_item_click(item)

    def today_recommend(self):
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT filename FROM images").fetchall()
        filenames = [row[0] for row in rows]
        if not filenames:
            QMessageBox.information(self, "提示", "没有图片可推荐")
            return
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        random.seed(today_str)
        chosen = random.choice(filenames)
        self.reset_to_all()
        self.load_images_by_filenames([chosen])
        if self.list_widget.count() > 0:
            item = self.list_widget.item(0)
            self.list_widget.setCurrentItem(item)
            self.on_item_click(item)

    def reset_to_all(self):
        for i in range(self.category_combo.count()):
            if self.category_combo.itemData(i) is None:
                self.category_combo.setCurrentIndex(i)
                break
        self.search_input.clear()
        self.filter_images()
        self.statusBar().showMessage("已显示全部图片", 2000)

    def show_tagcloud(self):
        freq = self.db.get_tag_frequencies()
        if not freq:
            QMessageBox.information(self, "提示", "暂无标签")
            return
        dlg = TagCloudDialog(freq, self)
        dlg.exec_()

    def toggle_favorite(self, checked):
        if not self.current_filename:
            QMessageBox.information(self, "提示", "请先单击选择图片")
            self.fav_btn.setChecked(False)
            return
        try:
            self.db.set_favorite(self.current_filename, checked)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"收藏操作失败: {e}")
            return
        item = self.list_widget.currentItem()
        if item:
            item.setData(Qt.UserRole+4, 1 if checked else 0)
            disp = item.data(Qt.UserRole+1)
            cat = item.data(Qt.UserRole+2)
            tags = item.data(Qt.UserRole+3)
            fav_mark = "❤️ " if checked else ""
            item.setText(f"{fav_mark}{disp}\n[{cat}] {tags}")
        self.statusBar().showMessage("已" + ("收藏" if checked else "取消收藏"), 2000)

    def export_favorites(self):
        favorites = self.db.get_favorites()
        if not favorites:
            QMessageBox.information(self, "提示", "收藏夹为空")
            return
        zip_path, _ = QFileDialog.getSaveFileName(self, "导出收藏夹", "favorites.zip", "ZIP文件 (*.zip)")
        if not zip_path:
            return
        try:
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                info_list = []
                for fn in favorites:
                    filepath = os.path.join(self.images_dir, fn)
                    if os.path.exists(filepath):
                        zipf.write(filepath, arcname=f"images/{fn}")
                        with self.db.get_connection() as conn:
                            row = conn.execute(
                                "SELECT display_name, category, tags FROM images WHERE filename=?", (fn,)
                            ).fetchone()
                        if row:
                            info_list.append({
                                'filename': fn,
                                'display_name': row[0],
                                'category': row[1],
                                'tags': row[2]
                            })
                zipf.writestr('metadata.json', json.dumps(info_list, ensure_ascii=False, indent=2))
            QMessageBox.information(self, "成功", f"已导出 {len(info_list)} 张图片")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def import_favorites(self):
        zip_path, _ = QFileDialog.getOpenFileName(self, "导入收藏夹", "", "ZIP文件 (*.zip)")
        if not zip_path:
            return
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                if 'metadata.json' not in zipf.namelist():
                    QMessageBox.critical(self, "错误", "无效的收藏夹文件")
                    return
                data = json.loads(zipf.read('metadata.json').decode('utf-8'))
                temp_dir = tempfile.mkdtemp()
                zipf.extractall(temp_dir)
                imported = 0
                for item in data:
                    src_img = os.path.join(temp_dir, 'images', item['filename'])
                    if os.path.exists(src_img):
                        base = item['filename']
                        name, ext = os.path.splitext(base)
                        dest = base
                        cnt = 1
                        while os.path.exists(os.path.join(self.images_dir, dest)):
                            dest = f"{name}_{cnt}{ext}"
                            cnt += 1
                        dest_path = os.path.join(self.images_dir, dest)
                        shutil.copy2(src_img, dest_path)
                        phash = calculate_phash(dest_path)
                        try:
                            self.db.add_image(dest, item['display_name'], item['category'], item['tags'], phash)
                            self.db.set_favorite(dest, True)
                            imported += 1
                        except DuplicateImageError:
                            os.remove(dest_path)
                            continue
                shutil.rmtree(temp_dir)
            QMessageBox.information(self, "成功", f"已导入 {imported} 张图片")
            self.filter_images()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入失败: {e}")

