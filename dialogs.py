import io
from typing import List, Dict, Tuple

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QDialogButtonBox, QShortcut, QScrollArea, QPushButton,
                             QWidget, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence, QPixmap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from wordcloud import WordCloud


class EditImageDialog(QDialog):
    """编辑图片分类和标签的对话框"""
    def __init__(self, old_category: str = "", old_tags: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑图片信息")
        self.setModal(True)
        self.resize(300, 150)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.category_edit = QLineEdit(old_category)
        self.category_edit.setPlaceholderText("可留空")
        form_layout.addRow("分类:", self.category_edit)

        self.tags_edit = QLineEdit(old_tags)
        self.tags_edit.setPlaceholderText("例如: 可爱, 初音未来")
        form_layout.addRow("标签 (逗号分隔):", self.tags_edit)
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        self.tags_edit.setFocus()

    def get_values(self) -> Tuple[str, str]:
        return self.category_edit.text().strip(), self.tags_edit.text().strip()


class TagSuggestDialog(QDialog):
    """推荐标签多选对话框"""
    def __init__(self, hot_tags: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择推荐标签")
        self.setModal(True)
        self.resize(400, 350)

        self.selected_tags = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("热门标签（可多选）:"))

        # 全选/取消按钮行
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        layout.addLayout(btn_layout)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self.tag_layout = QVBoxLayout(container)

        self.tag_buttons = []
        for tag in hot_tags:
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tag: self.toggle_tag(t, checked))
            self.tag_layout.addWidget(btn)
            self.tag_buttons.append(btn)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # 确定/取消
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+A"), self, self.select_all)
        QShortcut(QKeySequence("Ctrl+D"), self, self.deselect_all)

    def toggle_tag(self, tag: str, checked: bool):
        if checked and tag not in self.selected_tags:
            self.selected_tags.append(tag)
        elif not checked and tag in self.selected_tags:
            self.selected_tags.remove(tag)

    def select_all(self):
        for btn in self.tag_buttons:
            btn.setChecked(True)
            tag = btn.text()
            if tag not in self.selected_tags:
                self.selected_tags.append(tag)

    def deselect_all(self):
        for btn in self.tag_buttons:
            btn.setChecked(False)
        self.selected_tags.clear()

    def get_selected_tags(self) -> List[str]:
        return self.selected_tags


class TagCloudDialog(QDialog):
    """标签云展示对话框"""
    def __init__(self, tag_freq: Dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("标签云")
        self.setModal(True)
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        self.info_label = QLabel("正在生成词云...")
        layout.addWidget(self.info_label)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.hide()
        layout.addWidget(self.image_label)

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        layout.addWidget(self.close_btn)

        # 延迟生成，避免阻塞构造函数
        QTimer.singleShot(0, lambda: self.generate_wordcloud(tag_freq))

    def generate_wordcloud(self, tag_freq: Dict[str, int]):
        try:
            wc = WordCloud(width=550, height=400, background_color='white')
            wc.generate_from_frequencies(tag_freq)
            image = wc.to_image()
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            self.image_label.setPixmap(pixmap)
            self.image_label.show()
            self.info_label.hide()
            self.close_btn.setEnabled(True)
        except Exception as e:
            self.info_label.setText(f"生成词云失败: {e}")
            self.close_btn.setEnabled(True)
            QMessageBox.warning(self, "错误", f"无法生成词云: {e}")