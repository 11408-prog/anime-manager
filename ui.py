# ui.py
import qtawesome as qta
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
                             QLineEdit, QComboBox, QListWidget, QSplitter,
                             QWidget, QAbstractItemView)
from PyQt5.QtCore import Qt, QSize

# 浅色主题样式
LIGHT_STYLE = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #f0f2f5, stop:1 #e6e9f0);
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1e90ff, stop:1 #187bcd);
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 20px;
    font-weight: bold;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3aa0ff, stop:1 #1e90ff);
}
QPushButton:pressed {
    background: #0f6ab8;
}
QPushButton#batch_delete_btn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #ff4d4f, stop:1 #f5222d);
}
QLineEdit, QComboBox {
    padding: 8px 12px;
    border: 1px solid #d9d9d9;
    border-radius: 20px;
    background: white;
    selection-background-color: #1e90ff;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #1e90ff;
    border-width: 2px;
}
QListWidget {
    background: white;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 8px;
}
QListWidget::item {
    background: white;
    border: 1px solid #f0f0f0;
    border-radius: 12px;
    margin: 8px;
    padding: 8px;
}
QListWidget::item:hover {
    background: #f5f5f5;
    border-color: #1e90ff;
}
QListWidget::item:selected {
    background: #e6f7ff;
    border-color: #1e90ff;
    border-width: 2px;
}
"""

# 深色主题样式
DARK_STYLE = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #2d2d2d, stop:1 #1a1a1a);
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3c3c3c, stop:1 #2a2a2a);
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 8px 16px;
    border-radius: 20px;
    font-weight: bold;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #4a4a4a, stop:1 #3c3c3c);
    border-color: #1e90ff;
}
QPushButton#batch_delete_btn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #a13d3d, stop:1 #8b2c2c);
}
QLineEdit, QComboBox {
    padding: 8px 12px;
    border: 1px solid #555;
    border-radius: 20px;
    background: #3c3c3c;
    color: #e0e0e0;
    selection-background-color: #1e90ff;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #1e90ff;
    border-width: 2px;
}
QListWidget {
    background: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 12px;
    padding: 8px;
}
QListWidget::item {
    background: #3c3c3c;
    border: 1px solid #555;
    border-radius: 12px;
    margin: 8px;
    padding: 8px;
}
QListWidget::item:hover {
    background: #4a4a4a;
    border-color: #1e90ff;
}
QListWidget::item:selected {
    background: #1e3a5f;
    border-color: #1e90ff;
    border-width: 2px;
}
"""

def create_toolbar1(app):
    """创建第一行工具栏（添加、爬取、分类、搜索、主题切换、私密空间）"""
    toolbar = QHBoxLayout()

    # 添加图片按钮
    add_btn = QPushButton(" 添加图片")
    add_btn.setIcon(qta.icon('fa5s.plus-circle', color='white'))
    add_btn.clicked.connect(app.add_image)
    toolbar.addWidget(add_btn)

    # 爬取图片按钮
    crawler_btn = QPushButton(" 爬取图片")
    crawler_btn.setIcon(qta.icon('fa5s.spider', color='white'))
    crawler_btn.clicked.connect(app.open_crawler)
    toolbar.addWidget(crawler_btn)

    # 分类下拉框
    toolbar.addWidget(QLabel("分类:"))
    app.category_combo = QComboBox()
    app.category_combo.addItem("全部", None)
    app.category_combo.currentIndexChanged.connect(app.filter_images)
    toolbar.addWidget(app.category_combo)

    # 收藏筛选下拉框
    toolbar.addWidget(QLabel("收藏:"))
    app.fav_combo = QComboBox()
    app.fav_combo.addItem("全部", None)
    app.fav_combo.addItem("已收藏", 1)
    app.fav_combo.addItem("未收藏", 0)
    app.fav_combo.currentIndexChanged.connect(app.filter_images)
    toolbar.addWidget(app.fav_combo)

    # 搜索输入框
    toolbar.addWidget(QLabel("搜索标签:"))
    app.search_input = QLineEdit()
    app.search_input.setPlaceholderText("输入关键词...")
    app.search_input.textChanged.connect(app.filter_images)
    toolbar.addWidget(app.search_input)

    # 主题切换按钮
    app.theme_btn = QPushButton("🌙 深色模式")
    app.theme_btn.setCheckable(True)
    app.theme_btn.clicked.connect(app.toggle_theme)
    toolbar.addWidget(app.theme_btn)

    # 私密空间按钮
    private_btn = QPushButton("🔒 私密空间")
    private_btn.setIcon(qta.icon('fa5s.lock', color='white'))
    private_btn.clicked.connect(app.open_private_space)
    toolbar.addWidget(private_btn)

    toolbar.addStretch()
    return toolbar

def create_toolbar2(app):
    """创建第二行工具栏（批量操作、相似查找、随机漫游、导出导入等）"""
    toolbar = QHBoxLayout()

    # 批量删除按钮
    batch_delete_btn = QPushButton(" 批量删除")
    batch_delete_btn.setIcon(qta.icon('fa5s.trash-alt', color='white'))
    batch_delete_btn.setObjectName("batch_delete_btn")
    batch_delete_btn.clicked.connect(app.batch_delete)
    toolbar.addWidget(batch_delete_btn)

    # 全选按钮
    select_all_btn = QPushButton(" 全选")
    select_all_btn.setIcon(qta.icon('fa5s.check-square', color='white'))
    select_all_btn.clicked.connect(app.select_all)
    toolbar.addWidget(select_all_btn)

    # 取消全选按钮
    deselect_all_btn = QPushButton(" 取消全选")
    deselect_all_btn.setIcon(qta.icon('fa5s.square', color='white'))
    deselect_all_btn.clicked.connect(app.deselect_all)
    toolbar.addWidget(deselect_all_btn)

    # 查找相似按钮
    similar_btn = QPushButton(" 查找相似")
    similar_btn.setIcon(qta.icon('fa5s.search', color='white'))
    similar_btn.clicked.connect(app.find_similar_images)
    toolbar.addWidget(similar_btn)

    # 随机漫游按钮
    random_btn = QPushButton(" 随机漫游")
    random_btn.setIcon(qta.icon('fa5s.dice', color='white'))
    random_btn.clicked.connect(app.random_walk)
    toolbar.addWidget(random_btn)

    # 今日推荐按钮
    today_btn = QPushButton(" 今日推荐")
    today_btn.setIcon(qta.icon('fa5s.calendar-alt', color='white'))
    today_btn.clicked.connect(app.today_recommend)
    toolbar.addWidget(today_btn)

    # 显示全部按钮
    reset_btn = QPushButton(" 显示全部")
    reset_btn.setIcon(qta.icon('fa5s.sync-alt', color='white'))
    reset_btn.clicked.connect(app.reset_to_all)
    toolbar.addWidget(reset_btn)

    # 标签云按钮
    tagcloud_btn = QPushButton(" 标签云")
    tagcloud_btn.setIcon(qta.icon('fa5s.cloud', color='white'))
    tagcloud_btn.clicked.connect(app.show_tagcloud)
    toolbar.addWidget(tagcloud_btn)

    # 导出收藏按钮
    export_fav_btn = QPushButton(" 导出收藏")
    export_fav_btn.setIcon(qta.icon('fa5s.file-export', color='white'))
    export_fav_btn.clicked.connect(app.export_favorites)
    toolbar.addWidget(export_fav_btn)

    # 导入收藏按钮
    import_fav_btn = QPushButton(" 导入收藏")
    import_fav_btn.setIcon(qta.icon('fa5s.file-import', color='white'))
    import_fav_btn.clicked.connect(app.import_favorites)
    toolbar.addWidget(import_fav_btn)

    toolbar.addStretch()
    return toolbar

def create_main_splitter(app):
    """创建主分割区域（左侧图片网格 + 右侧预览区）"""
    splitter = QSplitter(Qt.Horizontal)

    # 左侧图片网格
    app.list_widget = QListWidget()
    app.list_widget.setViewMode(QListWidget.IconMode)
    app.list_widget.setIconSize(QSize(120, 120))
    app.list_widget.setGridSize(QSize(150, 180))
    app.list_widget.setResizeMode(QListWidget.Adjust)
    app.list_widget.setWordWrap(True)
    app.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
    app.list_widget.itemClicked.connect(app.on_item_click)
    app.list_widget.itemDoubleClicked.connect(app.edit_image)
    app.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
    app.list_widget.customContextMenuRequested.connect(app.show_context_menu)
    splitter.addWidget(app.list_widget)

    # 右侧预览区
    right = QWidget()
    right_layout = QVBoxLayout(right)

    app.image_label = QLabel("点击图片预览")
    app.image_label.setAlignment(Qt.AlignCenter)
    app.image_label.setStyleSheet("background: #f9f9f9; border:1px solid #ddd; border-radius:8px;")
    app.image_label.mouseDoubleClickEvent = app.on_image_double_click
    right_layout.addWidget(app.image_label)

    btn_layout = QHBoxLayout()
    fullscreen_btn = QPushButton(" 全屏查看")
    fullscreen_btn.setIcon(qta.icon('fa5s.expand', color='white'))
    fullscreen_btn.clicked.connect(app.show_fullscreen)
    btn_layout.addWidget(fullscreen_btn)

    download_btn = QPushButton(" 下载图片")
    download_btn.setIcon(qta.icon('fa5s.download', color='white'))
    download_btn.clicked.connect(app.download_image)
    btn_layout.addWidget(download_btn)

    app.fav_btn = QPushButton(" 收藏")
    app.fav_btn.setIcon(qta.icon('fa5s.heart', color='white'))
    app.fav_btn.setCheckable(True)
    app.fav_btn.clicked.connect(app.toggle_favorite)
    btn_layout.addWidget(app.fav_btn)

    right_layout.addLayout(btn_layout)
    splitter.addWidget(right)
    splitter.setSizes([700, 400])

    return splitter