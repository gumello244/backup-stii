import sys
import os

# Garante que o diretório raiz do projeto está no path,
# permitindo imports como "from core.deteccao import ..."
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from ui.main import App

if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = App()
    janela.show()
    sys.exit(app.exec_())
