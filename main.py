import sys
import logging
from PyQt5.QtWidgets import QApplication
from app import ImageApp

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = QApplication(sys.argv)
    win = ImageApp()
    win.show()
    sys.exit(app.exec_())