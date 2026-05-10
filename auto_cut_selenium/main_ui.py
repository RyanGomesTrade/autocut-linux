# -*- coding: utf-8 -*-
import sys
import os
import subprocess
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFrame, QMessageBox
)
from PySide6.QtCore import Qt

# Importando estilo do projeto pai para manter consistência
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from ui_styles import APPLE_MINIMAL_THEME
except ImportError:
    APPLE_MINIMAL_THEME = ""

class SeleniumApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Cut Selenium - Browser Automation")
        self.setMinimumSize(600, 400)
        
        self.init_ui()
        if APPLE_MINIMAL_THEME:
            self.setStyleSheet(APPLE_MINIMAL_THEME)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        header = QLabel("Gerenciador de Sessões (Browser)")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(header)
        
        desc = QLabel("Faça o login manual uma única vez para cada plataforma. O robô usará esses cookies para postar vídeos sem usar API.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)
        
        # YouTube Section
        yt_card = QFrame()
        yt_card.setObjectName("resultCard")
        yt_layout = QHBoxLayout(yt_card)
        yt_layout.addWidget(QLabel("YouTube Studio"))
        yt_layout.addStretch()
        
        self.btn_login_yt = QPushButton("Fazer Login / Atualizar Sessão")
        self.btn_login_yt.setObjectName("secondaryButton")
        self.btn_login_yt.clicked.connect(lambda: self.run_login("youtube"))
        yt_layout.addWidget(self.btn_login_yt)
        layout.addWidget(yt_card)
        
        # TikTok Section
        tt_card = QFrame()
        tt_card.setObjectName("resultCard")
        tt_layout = QHBoxLayout(tt_card)
        tt_layout.addWidget(QLabel("TikTok Web"))
        tt_layout.addStretch()
        
        self.btn_login_tt = QPushButton("Fazer Login / Atualizar Sessão")
        self.btn_login_tt.setObjectName("secondaryButton")
        self.btn_login_tt.clicked.connect(lambda: self.run_login("tiktok"))
        tt_layout.addWidget(self.btn_login_tt)
        layout.addWidget(tt_card)
        
        layout.addStretch()
        
        # Next Steps
        next_steps = QLabel("Após logar, o sistema estará pronto para processar a fila de upload.")
        next_steps.setStyleSheet("font-style: italic; color: #86868B;")
        layout.addWidget(next_steps)

    def run_login(self, platform):
        try:
            # Chama o script de sessão em um novo processo de terminal
            # No Linux, tentamos abrir um terminal para o input() funcionar
            script_path = os.path.join(os.path.dirname(__file__), "session_manager.py")
            
            # Comando para rodar em um terminal separado (ex: x-terminal-emulator ou gnome-terminal)
            # Adicionamos aspas em volta do script_path para lidar com espaços no caminho
            cmd = f"python3 '{script_path}' {platform}"
            subprocess.Popen(['x-terminal-emulator', '-e', f'bash -c "{cmd}; exec bash"'])
            
            QMessageBox.information(self, "Login", f"Um terminal foi aberto para o login no {platform}. Siga as instruções lá.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o terminal de login: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SeleniumApp()
    window.show()
    sys.exit(app.exec())
