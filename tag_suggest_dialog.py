from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QScrollArea, QWidget, QDialogButtonBox
from PyQt5.QtCore import Qt

class TagSuggestDialog(QDialog):
    def __init__(self, hot_tags, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择推荐标签")
        self.setModal(True)
        self.resize(400, 300)

        self.selected_tags = []

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("热门标签（可多选）:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self.tag_layout = QVBoxLayout(container)

        for tag in hot_tags:
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tag: self.toggle_tag(t, checked))
            self.tag_layout.addWidget(btn)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # 确定/取消
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_tag(self, tag, checked):
        if checked and tag not in self.selected_tags:
            self.selected_tags.append(tag)
        elif not checked and tag in self.selected_tags:
            self.selected_tags.remove(tag)

    def get_selected_tags(self):
        return self.selected_tags