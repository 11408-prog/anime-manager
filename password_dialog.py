from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtCore import Qt
import password  # 导入上面的密码模块

class PasswordDialog(QDialog):
    def __init__(self, mode='verify', parent=None):
        """
        mode: 'verify' 验证密码, 'set' 设置新密码
        """
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("私密空间" if mode == 'verify' else "设置私密空间密码")
        self.setModal(True)
        self.resize(300, 150)

        layout = QVBoxLayout(self)
        if mode == 'set':
            layout.addWidget(QLabel("请设置私密空间密码（之后进入需要此密码）:"))
        else:
            layout.addWidget(QLabel("请输入私密空间密码:"))

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_edit)

        if mode == 'set':
            layout.addWidget(QLabel("再次输入密码:"))
            self.confirm_edit = QLineEdit()
            self.confirm_edit.setEchoMode(QLineEdit.Password)
            layout.addWidget(self.confirm_edit)

        btn = QPushButton("确定")
        btn.clicked.connect(self.on_ok)
        layout.addWidget(btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def on_ok(self):
        if self.mode == 'verify':
            pwd = self.password_edit.text()
            if password.verify_password(pwd):
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "密码错误")
                self.password_edit.clear()
        else:  # set
            pwd = self.password_edit.text()
            confirm = self.confirm_edit.text()
            if not pwd:
                QMessageBox.warning(self, "错误", "密码不能为空")
                return
            if pwd != confirm:
                QMessageBox.warning(self, "错误", "两次输入的密码不一致")
                return
            password.set_password(pwd)
            QMessageBox.information(self, "成功", "密码设置成功！")
            self.accept()