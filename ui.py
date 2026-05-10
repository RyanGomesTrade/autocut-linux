# -*- coding: utf-8 -*-
import utf8_bootstrap
import os
import sys

# Desativa links simbólicos do HuggingFace para evitar erro [WinError 1314] no Windows
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import json
import logging
import subprocess
import traceback
from pathlib import Path

# Hook global para capturar erros não tratados e mostrar no log/console
def global_exception_handler(exctype, value, tb):
    logger.error("".join(traceback.format_exception(exctype, value, tb)))
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_handler

logger = logging.getLogger("viral_cutter.ui")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFileDialog, QFrame, QStackedWidget,
    QProgressBar, QPlainTextEdit, QScrollArea, QGridLayout,
    QComboBox, QCheckBox, QSpinBox, QLineEdit, QGroupBox,
    QSizePolicy, QSpacerItem, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QPixmap, QColor

# Local imports
from ui_styles import APPLE_MINIMAL_THEME
from ui_worker import PipelineWorker, DownloadWorker, BatchPipelineWorker
from cutter import EXPORT_PRESETS
from youtube_uploader import YouTubeUploader

class ResultCard(QFrame):
    """
    A card component to display a generated viral cut.
    """
    def __init__(self, cut_data):
        super().__init__()
        self.setObjectName("resultCard")
        self.cut_data = cut_data
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Placeholder for thumbnail (since we don't have them yet, or we'd need to generate)
        # For now, just a colored box or text
        thumb_label = QLabel("🎬 CLIP")
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet("background-color: #E5E5EA; border-radius: 6px; min-height: 120px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(thumb_label)

        # Title/Info
        title = QLabel(f"Corte #{self.cut_data.get('cut_index', 0)}")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        time_info = QLabel(f"⏱ {self.cut_data.get('duration', 0):.1f}s")
        time_info.setStyleSheet("color: #86868B; font-size: 12px;")
        layout.addWidget(time_info)

        # Actions
        btn_layout = QHBoxLayout()
        
        open_btn = QPushButton("Abrir")
        open_btn.setObjectName("secondaryButton")
        open_btn.clicked.connect(self.open_file)
        
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

    def open_file(self):
        file_path = self.cut_data.get("file") or self.cut_data.get("files", {}).get("final")
        if file_path and os.path.exists(file_path):
            if sys.platform == 'win32':
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])

class ViralCutterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Viral Cutter Pro")
        self.setMinimumSize(1000, 700)
        
        # Application State
        self.worker = None
        self.uploader = YouTubeUploader() # Inicializa o gerenciador de perfis
        self.config = {
            "input": "",
            "batch_list": None,
            "upload_youtube": False,
            "youtube_profile_index": 0, # Índice do perfil selecionado
            "schedule_interval": 0,
            "output": os.path.normpath(os.path.join(os.path.expanduser("~"), "Videos", "ViralCutter")),
            "whisper_model": "medium",
            "whisper_backend": "auto",
            "device": "cpu",
            "language": None,
            "model": "llama3",
            "ollama_host": "http://localhost:11434",
            "top_n": 10,
            "min_score": 40.0,
            "min_duration": 20.0,
            "max_duration": 65.0,
            "preset": "tiktok",
            "no_subtitles": False,
            "soft_subtitles": False,
            "no_silence_detect": False,
            "keep_temp": False,
            "skip_transcription": None,
            "skip_analysis": None,
            "ollama_timeout": 1200,
            "analysis_engine": "heuristic",
            "log_level": "INFO",
            "subtitle_style": "high_impact",
            # Edição avançada
            "visual_filter": "none",
            "bg_music": None,
            "bg_music_volume": 0.15,
            "fade_duration": 0.5,
            "progress_bar": False,
            "auto_frame": False,
            # Marca d'água
            "watermark_image":     None,
            "watermark_text":      None,
            "watermark_position":  "bottom_right",
            "watermark_opacity":   0.8,
            "watermark_scale":     1.0,
            "watermark_font_size": 40,
            "watermark_font_color": "white",
        }

        self.init_ui()
        self.setStyleSheet(APPLE_MINIMAL_THEME)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        
        # Logo / Title
        logo_label = QLabel("🎬 Viral Cutter")
        logo_label.setStyleSheet("font-size: 20px; font-weight: 800; color: #1D1D1F; padding: 10px 20px; margin-bottom: 20px;")
        sidebar_layout.addWidget(logo_label)

        # Nav Buttons
        self.nav_btns = []
        self.btn_dashboard = self._create_nav_btn("Dashboard", 0)
        self.btn_lote = self._create_nav_btn("Gerenciar Lote", 1) # Nova aba
        self.btn_settings = self._create_nav_btn("Configurações", 2)
        self.btn_progress = self._create_nav_btn("Progresso", 3)
        self.btn_results = self._create_nav_btn("Resultados", 4)
        
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_lote)
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addWidget(self.btn_progress)
        sidebar_layout.addWidget(self.btn_results)
        
        sidebar_layout.addStretch()
        
        status_box = QFrame()
        status_box.setStyleSheet("background-color: #E5E5EA; margin: 10px; border-radius: 8px; padding: 10px;")
        status_layout = QVBoxLayout(status_box)
        self.engine_status = QLabel("Ollama: Verificando...")
        self.engine_status.setStyleSheet("font-size: 11px; color: #86868B;")
        status_layout.addWidget(self.engine_status)
        sidebar_layout.addWidget(status_box)

        main_layout.addWidget(self.sidebar)

        # 2. Content Area (Stacked Widget)
        self.content_stack = QStackedWidget()
        
        self._setup_dashboard_page()
        self._setup_batch_page() # Nova página
        self._setup_settings_page()
        self._setup_progress_page()
        self._setup_results_page()
        
        main_layout.addWidget(self.content_stack)
        
        # Start at dashboard
        self.switch_page(0)
        self.check_engines()

    def _create_nav_btn(self, text, index):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
        self.nav_btns.append(btn)
        return btn

    def switch_page(self, index):
        self.content_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setProperty("active", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # --- Page Setup Methods ---

    def _setup_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        header = QLabel("Dashboard")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # Input File Card
        input_card = QFrame()
        input_card.setObjectName("resultCard")
        input_layout = QVBoxLayout(input_card)
        
        input_layout.addWidget(QLabel("Vídeo de Entrada ou Lista (.txt)"))
        file_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Selecione um arquivo MP4 ou list.txt...")
        self.input_edit.textChanged.connect(lambda t: self._update_config("input", t))
        
        browse_btn = QPushButton("Procurar")
        browse_btn.setObjectName("secondaryButton")
        browse_btn.clicked.connect(self.browse_input)
        
        file_row.addWidget(self.input_edit)
        file_row.addWidget(browse_btn)
        input_layout.addLayout(file_row)
        layout.addWidget(input_card)

        # YouTube Download Card
        yt_card = QFrame()
        yt_card.setObjectName("resultCard")
        yt_layout = QVBoxLayout(yt_card)
        
        yt_layout.addWidget(QLabel("Importar do YouTube"))
        yt_row = QHBoxLayout()
        self.yt_url_edit = QLineEdit()
        self.yt_url_edit.setPlaceholderText("Cole o link do vídeo aqui...")
        
        self.yt_dl_btn = QPushButton("Baixar")
        self.yt_dl_btn.setObjectName("secondaryButton")
        self.yt_dl_btn.clicked.connect(self.start_youtube_download)
        
        yt_row.addWidget(self.yt_url_edit)
        yt_row.addWidget(self.yt_dl_btn)
        yt_layout.addLayout(yt_row)
        
        self.yt_progress = QProgressBar()
        self.yt_progress.setVisible(False)
        self.yt_progress.setFixedHeight(4)
        self.yt_progress.setTextVisible(False)
        yt_layout.addWidget(self.yt_progress)
        
        layout.addWidget(yt_card)

        # Output Dir Card
        output_card = QFrame()
        output_card.setObjectName("resultCard")
        output_layout = QVBoxLayout(output_card)
        
        output_layout.addWidget(QLabel("Pasta de Saída"))
        dir_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setText(self.config["output"])
        self.output_edit.textChanged.connect(lambda t: self._update_config("output", t))
        
        out_browse_btn = QPushButton("Mudar")
        out_browse_btn.setObjectName("secondaryButton")
        out_browse_btn.clicked.connect(self.browse_output)
        
        dir_row.addWidget(self.output_edit)
        dir_row.addWidget(out_browse_btn)
        output_layout.addLayout(dir_row)
        layout.addWidget(output_card)

        # Quick Settings Summary
        layout.addWidget(QLabel("Configurações Rápidas"))
        quick_grid = QGridLayout()
        quick_grid.setColumnStretch(0, 0)
        quick_grid.setColumnStretch(1, 1)
        quick_grid.setHorizontalSpacing(16)
        quick_grid.setVerticalSpacing(10)
        
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(EXPORT_PRESETS.keys()))
        self.combo_preset.setCurrentText(self.config["preset"])
        self.combo_preset.currentTextChanged.connect(lambda t: self._update_config("preset", t))
        
        quick_grid.addWidget(QLabel("Formato (Preset):"), 0, 0)
        quick_grid.addWidget(self.combo_preset, 0, 1)
        
        quick_grid.addWidget(QLabel("Estilo Legenda:"), 1, 0)
        self.combo_subs = QComboBox()
        self.combo_subs.addItems(["Alto Impacto (Viral)", "Clássico (Burn-in)", "Soft (Rápido)", "Nenhuma"])
        style_map = {"high_impact": 0, "hardcoded": 1, "soft": 2, "none": 3}
        self.combo_subs.setCurrentIndex(style_map.get(self.config["subtitle_style"], 0))
        self.combo_subs.currentIndexChanged.connect(self.update_sub_style)
        quick_grid.addWidget(self.combo_subs, 1, 1)

        self.check_resume = QCheckBox("Pular transcrição (usar cache se disponível)")
        self.check_resume.setToolTip("Se marcado, o sistema tentará usar a transcrição já realizada na pasta de saída.")
        self.check_resume.toggled.connect(self.toggle_resume)
        quick_grid.addWidget(self.check_resume, 2, 0, 1, 2)
        
        self.check_upload = QCheckBox("Upload automático para o YouTube")
        self.check_upload.setToolTip("Somente ativado para processamento em lote (lista).")
        self.check_upload.setChecked(self.config.get("upload_youtube", False))
        self.check_upload.toggled.connect(lambda b: self._update_config("upload_youtube", b))
        quick_grid.addWidget(self.check_upload, 3, 0, 1, 2)
        
        layout.addLayout(quick_grid)
        layout.addStretch()

        # Start Button
        self.start_btn = QPushButton("GERAR CORTES VIRAIS")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setMinimumHeight(60)
        self.start_btn.clicked.connect(self.start_pipeline)
        layout.addWidget(self.start_btn)

        self.content_stack.addWidget(page)

    def _setup_batch_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        header = QLabel("Gerenciador de Lote")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # Actions Row
        actions_row = QHBoxLayout()
        add_btn = QPushButton("+ Adicionar URL")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(lambda: self.add_batch_row())
        
        import_btn = QPushButton("📂 Importar list.txt")
        import_btn.setObjectName("secondaryButton")
        import_btn.clicked.connect(self.import_batch_list)
        
        clear_btn = QPushButton("Limpar Tudo")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.clicked.connect(lambda: self.batch_table.setRowCount(0))
        
        save_btn = QPushButton("💾 Salvar Lista")
        save_btn.setObjectName("secondaryButton")
        save_btn.clicked.connect(self.save_batch_list)
        
        actions_row.addWidget(add_btn)
        actions_row.addWidget(import_btn)
        actions_row.addWidget(save_btn)
        actions_row.addStretch()
        actions_row.addWidget(clear_btn)
        layout.addLayout(actions_row)

        # Batch Table
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels(["URL do Vídeo", "Formato (Preset)", "Título Base / Prefixo", "Ações"])
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.batch_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.batch_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.batch_table.setColumnWidth(3, 100)
        self.batch_table.verticalHeader().setDefaultSectionSize(50) # Altura das linhas
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.setShowGrid(False)
        self.batch_table.setStyleSheet("""
            QTableWidget {
                background-color: white; 
                border-radius: 12px; 
                border: 1px solid #E5E5EA;
                gridline-color: transparent;
            }
            QHeaderView::section {
                background-color: #F5F5F7;
                padding: 10px;
                border: none;
                border-bottom: 1px solid #E5E5EA;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.batch_table)

        # Batch Controls
        bottom_row = QVBoxLayout()
        
        # Youtube Profile Selector Row
        yt_profile_row = QHBoxLayout()
        yt_profile_row.addWidget(QLabel("Canal do YouTube:"))
        self.combo_yt_profile = QComboBox()
        self._refresh_yt_profiles()
        self.combo_yt_profile.currentIndexChanged.connect(lambda i: self._update_config("youtube_profile_index", i))
        yt_profile_row.addWidget(self.combo_yt_profile)
        
        add_profile_btn = QPushButton("+ Novo Canal")
        add_profile_btn.setObjectName("secondaryButton")
        add_profile_btn.clicked.connect(self.show_add_profile_dialog)
        yt_profile_row.addWidget(add_profile_btn)
        
        remove_profile_btn = QPushButton("Remover")
        remove_profile_btn.setStyleSheet("color: #FF3B30;") # Vermelho Apple
        remove_profile_btn.clicked.connect(self.remove_current_profile)
        yt_profile_row.addWidget(remove_profile_btn)
        
        yt_profile_row.addStretch()
        
        bottom_row.addLayout(yt_profile_row)

        controls_row = QHBoxLayout()
        self.batch_upload_check = QCheckBox("Upload automático para YouTube")
        self.batch_upload_check.setChecked(self.config.get("upload_youtube", False))
        self.batch_upload_check.toggled.connect(lambda b: self._update_config("upload_youtube", b))
        
        schedule_layout = QHBoxLayout()
        schedule_layout.addWidget(QLabel("Agendar (intervalo em horas):"))
        self.schedule_spin = QSpinBox()
        self.schedule_spin.setRange(0, 72)
        self.schedule_spin.setSuffix(" h")
        self.schedule_spin.setValue(self.config.get("schedule_interval", 0))
        self.schedule_spin.valueChanged.connect(lambda v: self._update_config("schedule_interval", v))
        schedule_layout.addWidget(self.schedule_spin)
        
        self.start_batch_btn = QPushButton("INICIAR PROCESSAMENTO EM LOTE")
        self.start_batch_btn.setObjectName("primaryButton")
        self.start_batch_btn.setMinimumHeight(50)
        self.start_batch_btn.clicked.connect(self.start_batch_pipeline)
        
        controls_row.addWidget(self.batch_upload_check)
        controls_row.addLayout(schedule_layout)
        controls_row.addStretch()
        controls_row.addWidget(self.start_batch_btn)
        
        bottom_row.addLayout(controls_row)
        layout.addLayout(bottom_row)

        self.content_stack.addWidget(page)

    def _refresh_yt_profiles(self):
        """Atualiza o combobox de perfis do YouTube."""
        self.combo_yt_profile.clear()
        for p in self.uploader.profiles:
            self.combo_yt_profile.addItem(p["name"])
        self.combo_yt_profile.setCurrentIndex(self.config.get("youtube_profile_index", 0))

    def show_add_profile_dialog(self):
        """Mostra um diálogo simples para adicionar um novo perfil do YouTube."""
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Adicionar Novo Canal")
        layout = QFormLayout(dialog)
        
        # Sugere nomes baseados na quantidade de perfis
        next_idx = len(self.uploader.profiles) + 1
        name_edit = QLineEdit(f"Canal {next_idx}")
        
        # Layout para o arquivo de segredos com botão de procurar
        secrets_row = QHBoxLayout()
        secrets_edit = QLineEdit("client_secrets.json")
        browse_secrets_btn = QPushButton("...")
        browse_secrets_btn.setFixedWidth(30)
        browse_secrets_btn.clicked.connect(lambda: self._browse_for_file(secrets_edit, "Segredos do Google (JSON)", "*.json"))
        secrets_row.addWidget(secrets_edit)
        secrets_row.addWidget(browse_secrets_btn)
        
        token_edit = QLineEdit(f"token_canal_{next_idx}.pickle")
        
        layout.addRow("Nome do Canal:", name_edit)
        layout.addRow("Arquivo de Segredos:", secrets_row)
        layout.addRow("Arquivo de Token:", token_edit)
        
        info_label = QLabel("Dica: O nome que aparece no Google (v1 ou v2) depende de qual arquivo JSON você selecionar.")
        info_label.setStyleSheet("color: #007AFF; font-size: 11px; font-weight: bold;")
        layout.addRow(info_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            name = name_edit.text().strip()
            secrets = secrets_edit.text().strip()
            token = token_edit.text().strip()
            
            if name and secrets and token:
                self.uploader.add_profile(name, secrets, token)
                self._refresh_yt_profiles()
                # Tenta autenticar imediatamente para gerar o token
                self.uploader.authenticate(len(self.uploader.profiles) - 1)
                self.combo_yt_profile.setCurrentIndex(len(self.uploader.profiles) - 1)

    def remove_current_profile(self):
        """Remove o perfil selecionado atualmente."""
        idx = self.combo_yt_profile.currentIndex()
        if idx < 0: return
        
        profile_name = self.uploader.profiles[idx]["name"]
        confirm = QMessageBox.question(
            self, "Confirmar Remoção",
            f"Deseja realmente remover o canal '{profile_name}'?\nIsso também apagará o arquivo de token local.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            self.uploader.remove_profile(idx)
            self._refresh_yt_profiles()
            self._update_config("youtube_profile_index", self.combo_yt_profile.currentIndex())

    def _browse_for_file(self, line_edit, name, pattern):
        """Abre seletor de arquivos e atualiza o line_edit."""
        path, _ = QFileDialog.getOpenFileName(self, f"Selecionar {name}", "", f"{name} ({pattern})")
        if path:
            # Tenta salvar apenas o nome do arquivo se estiver no diretório atual
            root = os.getcwd()
            if path.startswith(root):
                path = os.path.relpath(path, root)
            line_edit.setText(path)

    def add_batch_row(self, url="", preset="shorts", title=""):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        
        # URL
        url_edit = QLineEdit(url)
        url_edit.setPlaceholderText("https://youtube.com/...")
        url_edit.setStyleSheet("border: 1px solid #E5E5EA; padding: 8px; border-radius: 6px; background: white;")
        self.batch_table.setCellWidget(row, 0, url_edit)
        
        # Preset
        preset_combo = QComboBox()
        preset_combo.addItems(list(EXPORT_PRESETS.keys()))
        preset_combo.setCurrentText(preset)
        preset_combo.setStyleSheet("padding: 5px; min-width: 120px;")
        self.batch_table.setCellWidget(row, 1, preset_combo)
        
        # Title
        title_edit = QLineEdit(title)
        title_edit.setPlaceholderText("Opcional: Prefixo do título")
        title_edit.setStyleSheet("border: 1px solid #E5E5EA; padding: 8px; border-radius: 6px; background: white;")
        self.batch_table.setCellWidget(row, 2, title_edit)
        
        # Remove Btn
        remove_btn = QPushButton("Remover")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet("""
            QPushButton {
                color: #FF3B30; 
                font-weight: bold; 
                border: none; 
                background: transparent;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        remove_btn.clicked.connect(lambda: self.batch_table.removeRow(self.batch_table.currentRow() if self.batch_table.currentRow() >= 0 else row))
        self.batch_table.setCellWidget(row, 3, remove_btn)

    def save_batch_list(self):
        """Salva o conteúdo da tabela de volta para um arquivo .txt"""
        if self.batch_table.rowCount() == 0:
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Lista", "minha_lista.txt", "Texto (*.txt)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("# Lista gerada pelo Viral Cutter\n")
                    for row in range(self.batch_table.rowCount()):
                        url_widget = self.batch_table.cellWidget(row, 0)
                        title_widget = self.batch_table.cellWidget(row, 2)
                        
                        if isinstance(url_widget, QLineEdit):
                            url = url_widget.text().strip()
                            prefix = title_widget.text().strip() if isinstance(title_widget, QLineEdit) else ""
                            
                            if url:
                                line = url
                                if prefix:
                                    line += f" # {prefix}"
                                f.write(line + "\n")
                
                logger.info(f"Lista salva com sucesso em: {path}")
            except Exception as e:
                logger.error(f"Erro ao salvar lista: {e}")

    def import_batch_list(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar Lista", "", "Texto (*.txt)")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Divide a linha no '#' para separar URL de um possível título/comentário
                        parts = line.split('#', 1)
                        url = parts[0].strip()
                        title = parts[1].strip() if len(parts) > 1 else ""
                        
                        if url:
                            self.add_batch_row(url=url, preset=self.config["preset"], title=title)

    def start_batch_pipeline(self):
        jobs = []
        for row in range(self.batch_table.rowCount()):
            url = self.batch_table.cellWidget(row, 0).text().strip()
            preset = self.batch_table.cellWidget(row, 1).currentText()
            title = self.batch_table.cellWidget(row, 2).text().strip()
            if url:
                jobs.append({"url": url, "preset": preset, "title_prefix": title})
        
        if not jobs:
            self.status_label.setText("Erro: Adicione pelo menos um vídeo ao lote.")
            return

        self.config["batch_jobs"] = jobs
        
        # UI Setup
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Iniciando lote...")
        self.switch_page(3) # Progresso
        
        # Start Worker
        self.worker = BatchPipelineWorker(self.config)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.status_label.setText)
        self.worker.finished_signal.connect(self.on_pipeline_finished)
        
        self.start_batch_btn.setEnabled(False)
        self.worker.start()


    def _setup_settings_page(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        header = QLabel("Configurações Avançadas")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # 1. Transcrição (Whisper)
        whisper_group = QGroupBox("🤖 Transcrição (Whisper)")
        w_layout = QGridLayout(whisper_group)
        
        w_layout.addWidget(QLabel("Modelo:"), 0, 0)
        self.combo_w_model = QComboBox()
        self.combo_w_model.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        self.combo_w_model.setCurrentText(self.config["whisper_model"])
        self.combo_w_model.currentTextChanged.connect(lambda t: self._update_config("whisper_model", t))
        w_layout.addWidget(self.combo_w_model, 0, 1)

        w_layout.addWidget(QLabel("Dispositivo:"), 1, 0)
        self.combo_device = QComboBox()
        self.combo_device.addItems(["cpu", "cuda"])
        self.combo_device.currentTextChanged.connect(lambda t: self._update_config("device", t))
        w_layout.addWidget(self.combo_device, 1, 1)
        
        layout.addWidget(whisper_group)

        # 2. Análise (Ollama / Heurística)
        ollama_group = QGroupBox("🧠 Inteligência Artificial / Análise")
        o_layout = QGridLayout(ollama_group)
        
        o_layout.addWidget(QLabel("Motor de Análise:"), 0, 0)
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Ollama (IA)", "Heurística (Sem IA - Rápido)"])
        self.combo_engine.setCurrentIndex(0 if self.config["analysis_engine"] == "ollama" else 1)
        self.combo_engine.currentIndexChanged.connect(lambda i: self._update_config("analysis_engine", "ollama" if i == 0 else "heuristic"))
        o_layout.addWidget(self.combo_engine, 0, 1)

        o_layout.addWidget(QLabel("Modelo Ollama:"), 1, 0)
        self.edit_o_model = QLineEdit(self.config["model"])
        self.edit_o_model.textChanged.connect(lambda t: self._update_config("model", t))
        o_layout.addWidget(self.edit_o_model, 1, 1)

        o_layout.addWidget(QLabel("Host URL:"), 2, 0)
        self.edit_o_host = QLineEdit(self.config["ollama_host"])
        self.edit_o_host.textChanged.connect(lambda t: self._update_config("ollama_host", t))
        o_layout.addWidget(self.edit_o_host, 2, 1)

        o_layout.addWidget(QLabel("Timeout (s):"), 3, 0)
        self.spin_o_timeout = QSpinBox()
        self.spin_o_timeout.setRange(30, 3600)
        self.spin_o_timeout.setValue(self.config["ollama_timeout"])
        self.spin_o_timeout.valueChanged.connect(lambda v: self._update_config("ollama_timeout", v))
        o_layout.addWidget(self.spin_o_timeout, 3, 1)
        
        layout.addWidget(ollama_group)

        # 3. Cortes e Legendas
        cuts_group = QGroupBox("✂ Parâmetros de Cortes e Legendas")
        c_layout = QGridLayout(cuts_group)
        
        c_layout.addWidget(QLabel("Número de cortes (top-n):"), 0, 0)
        self.spin_topn = QSpinBox()
        self.spin_topn.setRange(1, 50)
        self.spin_topn.setValue(self.config["top_n"])
        self.spin_topn.valueChanged.connect(lambda v: self._update_config("top_n", v))
        c_layout.addWidget(self.spin_topn, 0, 1)

        c_layout.addWidget(QLabel("Duração Mín (s):"), 1, 0)
        self.spin_min_d = QSpinBox()
        self.spin_min_d.setRange(5, 300)
        self.spin_min_d.setValue(int(self.config["min_duration"]))
        self.spin_min_d.valueChanged.connect(lambda v: self._update_config("min_duration", float(v)))
        c_layout.addWidget(self.spin_min_d, 1, 1)

        c_layout.addWidget(QLabel("Duração Máx (s):"), 1, 2)
        self.spin_max_d = QSpinBox()
        self.spin_max_d.setRange(5, 600)
        self.spin_max_d.setValue(int(self.config["max_duration"]))
        self.spin_max_d.valueChanged.connect(lambda v: self._update_config("max_duration", float(v)))
        c_layout.addWidget(self.spin_max_d, 1, 3)
        
        layout.addWidget(cuts_group)

        # 4. Outros
        other_group = QGroupBox("🛠 Opções Adicionais")
        ot_layout = QVBoxLayout(other_group)
        
        self.check_silence = QCheckBox("Detectar silêncio e ajustar cortes")
        self.check_silence.setChecked(not self.config["no_silence_detect"])
        self.check_silence.toggled.connect(lambda b: self._update_config("no_silence_detect", not b))
        ot_layout.addWidget(self.check_silence)
        
        layout.addWidget(other_group)

        # 5. Edição Estilo Shorts
        shorts_group = QGroupBox("✨ Edição Estilo Shorts (Automática)")
        s_layout = QGridLayout(shorts_group)

        s_layout.addWidget(QLabel("Filtro Visual:"), 0, 0)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["none", "vibrant", "cinematic", "warm"])
        self.combo_filter.currentTextChanged.connect(lambda t: self._update_config("visual_filter", t))
        s_layout.addWidget(self.combo_filter, 0, 1)

        s_layout.addWidget(QLabel("Música de Fundo:"), 1, 0)
        music_row = QHBoxLayout()
        self.music_edit = QLineEdit()
        self.music_edit.setPlaceholderText("Pasta com MP3s...")
        self.music_edit.textChanged.connect(lambda t: self._update_config("bg_music", t))
        
        browse_music_btn = QPushButton("Abrir")
        browse_music_btn.setObjectName("secondaryButton")
        browse_music_btn.clicked.connect(self.browse_music)
        
        music_row.addWidget(self.music_edit)
        music_row.addWidget(browse_music_btn)
        s_layout.addLayout(music_row, 1, 1)

        s_layout.addWidget(QLabel("Volume Música:"), 2, 0)
        self.spin_volume = QSpinBox()
        self.spin_volume.setRange(0, 100)
        self.spin_volume.setValue(int(self.config["bg_music_volume"] * 100))
        self.spin_volume.valueChanged.connect(lambda v: self._update_config("bg_music_volume", v / 100.0))
        s_layout.addWidget(self.spin_volume, 2, 1)

        self.check_progress = QCheckBox("Adicionar Barra de Progresso")
        self.check_progress.setChecked(self.config["progress_bar"])
        self.check_progress.toggled.connect(lambda b: self._update_config("progress_bar", b))
        s_layout.addWidget(self.check_progress, 3, 0, 1, 2)

        self.check_autoframe = QCheckBox("Auto-Framing (Seguir Rosto)")
        self.check_autoframe.setToolTip("No modo retrato, em vez de focar no meio, a IA tentará rastrear o rosto de quem está falando.")
        self.check_autoframe.setChecked(self.config["auto_frame"])
        self.check_autoframe.toggled.connect(lambda b: self._update_config("auto_frame", b))
        s_layout.addWidget(self.check_autoframe, 4, 0, 1, 2)

        layout.addWidget(shorts_group)

        # 6. Marca d'água
        wm_group = QGroupBox("💧 Marca d'água")
        wm_layout = QGridLayout(wm_group)

        # Imagem
        wm_layout.addWidget(QLabel("Imagem (PNG/WebP):"), 0, 0)
        wm_img_row = QHBoxLayout()
        self.wm_image_edit = QLineEdit()
        self.wm_image_edit.setPlaceholderText("Caminho para logo com transparência...")
        self.wm_image_edit.setText(self.config.get("watermark_image") or "")
        self.wm_image_edit.textChanged.connect(
            lambda t: self._update_config("watermark_image", t if t.strip() else None)
        )
        wm_browse_btn = QPushButton("Abrir")
        wm_browse_btn.setObjectName("secondaryButton")
        wm_browse_btn.clicked.connect(self.browse_watermark_image)
        wm_img_row.addWidget(self.wm_image_edit)
        wm_img_row.addWidget(wm_browse_btn)
        wm_layout.addLayout(wm_img_row, 0, 1)

        # Texto
        wm_layout.addWidget(QLabel("Texto:"), 1, 0)
        self.wm_text_edit = QLineEdit()
        self.wm_text_edit.setPlaceholderText("Ex: @meucanal")
        self.wm_text_edit.setText(self.config.get("watermark_text") or "")
        self.wm_text_edit.textChanged.connect(
            lambda t: self._update_config("watermark_text", t if t.strip() else None)
        )
        wm_layout.addWidget(self.wm_text_edit, 1, 1)

        # Posição
        wm_layout.addWidget(QLabel("Posição:"), 2, 0)
        self.combo_wm_pos = QComboBox()
        wm_positions = ["bottom_right", "bottom_left", "top_right", "top_left",
                        "bottom_center", "top_center", "center"]
        wm_pos_labels = ["Inferior Direito", "Inferior Esquerdo", "Superior Direito",
                         "Superior Esquerdo", "Inferior Centro", "Superior Centro", "Centro"]
        for pos, lbl in zip(wm_positions, wm_pos_labels):
            self.combo_wm_pos.addItem(lbl, pos)
        cur_pos = self.config.get("watermark_position", "bottom_right")
        idx = wm_positions.index(cur_pos) if cur_pos in wm_positions else 0
        self.combo_wm_pos.setCurrentIndex(idx)
        self.combo_wm_pos.currentIndexChanged.connect(
            lambda i: self._update_config("watermark_position", self.combo_wm_pos.itemData(i))
        )
        wm_layout.addWidget(self.combo_wm_pos, 2, 1)

        # Opacidade
        wm_layout.addWidget(QLabel("Opacidade (%):"), 3, 0)
        self.spin_wm_opacity = QSpinBox()
        self.spin_wm_opacity.setRange(10, 100)
        self.spin_wm_opacity.setSuffix("%")
        self.spin_wm_opacity.setValue(int(self.config.get("watermark_opacity", 0.8) * 100))
        self.spin_wm_opacity.valueChanged.connect(
            lambda v: self._update_config("watermark_opacity", v / 100.0)
        )
        wm_layout.addWidget(self.spin_wm_opacity, 3, 1)

        # Escala da imagem
        wm_layout.addWidget(QLabel("Escala da Imagem (%):"), 4, 0)
        self.spin_wm_scale = QSpinBox()
        self.spin_wm_scale.setRange(10, 300)
        self.spin_wm_scale.setSuffix("%")
        self.spin_wm_scale.setValue(int(self.config.get("watermark_scale", 1.0) * 100))
        self.spin_wm_scale.valueChanged.connect(
            lambda v: self._update_config("watermark_scale", v / 100.0)
        )
        wm_layout.addWidget(self.spin_wm_scale, 4, 1)

        # Tamanho da fonte
        wm_layout.addWidget(QLabel("Tamanho da Fonte:"), 5, 0)
        self.spin_wm_font = QSpinBox()
        self.spin_wm_font.setRange(10, 200)
        self.spin_wm_font.setValue(self.config.get("watermark_font_size", 40))
        self.spin_wm_font.valueChanged.connect(
            lambda v: self._update_config("watermark_font_size", v)
        )
        wm_layout.addWidget(self.spin_wm_font, 5, 1)

        # Cor do texto
        wm_layout.addWidget(QLabel("Cor do Texto:"), 6, 0)
        self.combo_wm_color = QComboBox()
        wm_colors = [("Branco", "white"), ("Preto", "black"),
                     ("Amarelo", "yellow"), ("Vermelho", "red"), ("Ciano", "cyan")]
        for lbl, val in wm_colors:
            self.combo_wm_color.addItem(lbl, val)
        cur_color = self.config.get("watermark_font_color", "white")
        color_vals = [v for _, v in wm_colors]
        cidx = color_vals.index(cur_color) if cur_color in color_vals else 0
        self.combo_wm_color.setCurrentIndex(cidx)
        self.combo_wm_color.currentIndexChanged.connect(
            lambda i: self._update_config("watermark_font_color", self.combo_wm_color.itemData(i))
        )
        wm_layout.addWidget(self.combo_wm_color, 6, 1)

        layout.addWidget(wm_group)

        layout.addStretch()
        
        scroll.setWidget(container)
        self.content_stack.addWidget(scroll)

    def _setup_progress_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        header = QLabel("Processamento")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        self.status_label = QLabel("Aguardando início...")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Logs em Tempo Real"))
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        self.content_stack.addWidget(page)

    def _setup_results_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        header = QLabel("Cortes Gerados")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # Scrollable Area for results
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        self.results_scroll.setStyleSheet("background-color: transparent;")
        
        self.results_container = QWidget()
        self.results_grid = QGridLayout(self.results_container)
        self.results_grid.setSpacing(15)
        self.results_scroll.setWidget(self.results_container)
        
        layout.addWidget(self.results_scroll)

        btn_row = QHBoxLayout()
        open_folder_btn = QPushButton("Abrir Pasta de Saída")
        open_folder_btn.setObjectName("secondaryButton")
        open_folder_btn.clicked.connect(self.open_output_folder)
        
        btn_row.addStretch()
        btn_row.addWidget(open_folder_btn)
        layout.addLayout(btn_row)

        self.content_stack.addWidget(page)

    # --- Slots and Logic ---

    def _update_config(self, key, value):
        self.config[key] = value

    def update_sub_style(self, index):
        styles = ["high_impact", "hardcoded", "soft", "none"]
        self.config["subtitle_style"] = styles[index]
        self.config["no_subtitles"] = (styles[index] == "none")
        self.config["soft_subtitles"] = (styles[index] == "soft")

    def browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Vídeo ou Lista", "", "Arquivos (*.mp4 *.mkv *.mov *.avi *.txt)")
        if path:
            self.input_edit.setText(path)

    def toggle_resume(self, checked):
        if checked:
            # Tenta localizar o arquivo pkl na pasta de saída
            pkl_path = os.path.normpath(os.path.join(self.config["output"], "transcript.pkl"))
            if os.path.exists(pkl_path):
                self.config["skip_transcription"] = pkl_path
                self.append_log(f"INFO: Cache de transcrição configurado: {pkl_path}")
            else:
                if hasattr(self, 'status_label'):
                    self.status_label.setText("⚠ Arquivo transcript.pkl não encontrado.")
                self.append_log(f"WARNING: Não foi possível encontrar cache em {self.config['output']}")
                self.check_resume.setChecked(False)
        else:
            self.config["skip_transcription"] = None

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída", self.config["output"])
        if path:
            self.output_edit.setText(path)

    def browse_music(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Músicas", self.config.get("bg_music", ""))
        if path:
            self.music_edit.setText(path)

    def browse_watermark_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Imagem da Marca d'água", "",
            "Imagens (*.png *.webp *.jpg *.jpeg)"
        )
        if path:
            self.wm_image_edit.setText(path)

    def start_youtube_download(self):
        url = self.yt_url_edit.text().strip()
        if not url:
            return
            
        self.yt_dl_btn.setEnabled(False)
        self.yt_progress.setVisible(True)
        self.yt_progress.setValue(0)
        
        # We need a place to save the downloaded videos
        downloads_dir = os.path.join(self.config["output"], "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        
        self.dl_worker = DownloadWorker(url, downloads_dir)
        self.dl_worker.progress_signal.connect(self.yt_progress.setValue)
        self.dl_worker.finished_signal.connect(self.on_download_finished)
        self.dl_worker.start()

    def on_download_finished(self, success, file_path):
        self.yt_dl_btn.setEnabled(True)
        self.yt_progress.setVisible(False)
        if success:
            self.input_edit.setText(file_path)
            self.yt_url_edit.clear()
            self.status_label.setText(f"Download concluído: {os.path.basename(file_path)}")
        else:
            self.status_label.setText("Erro ao baixar vídeo do YouTube.")

    def open_output_folder(self):
        path = self.config["output"]
        if os.path.exists(path):
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', path])
            else:
                subprocess.run(['xdg-open', path])

    def check_engines(self):
        """Simple async check if Ollama is running — runs in a thread to avoid UI freeze."""
        from PySide6.QtCore import QThread

        class _OllamaChecker(QThread):
            done = Signal(bool)
            def run(self):
                try:
                    import urllib.request
                    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
                    self.done.emit(True)
                except Exception:
                    self.done.emit(False)

        def _apply(ok):
            if ok:
                self.engine_status.setText("✓ Ollama: Rodando")
                self.engine_status.setStyleSheet("font-size: 11px; color: #34C759;")
            else:
                self.engine_status.setText("✗ Ollama: Desconectado")
                self.engine_status.setStyleSheet("font-size: 11px; color: #FF3B30;")

        self._engine_checker = _OllamaChecker()
        self._engine_checker.done.connect(_apply)
        self._engine_checker.start()

    def start_pipeline(self):
        if not self.config["input"] or not os.path.exists(self.config["input"]):
            self.status_label.setText("Erro: Selecione um arquivo de entrada válido.")
            self.switch_page(0)
            return

        is_batch = self.config["input"].endswith(".txt")
        if is_batch:
            self.config["batch_list"] = self.config["input"]
        else:
            self.config["batch_list"] = None

        # Prepare UI
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Iniciando...")
        self.switch_page(3) # Move to progress page (was 2)
        
        # Clear results from previous run (itemAt can return spacers with no widget)
        for i in reversed(range(self.results_grid.count())):
            item = self.results_grid.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

        # Create and start worker
        if is_batch:
            self.worker = BatchPipelineWorker(self.config)
        else:
            self.worker = PipelineWorker(self.config)
            
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.status_signal.connect(self.status_label.setText)
        self.worker.results_ready_signal.connect(self.display_results)
        self.worker.finished_signal.connect(self.on_pipeline_finished)
        
        self.start_btn.setEnabled(False)
        self.worker.start()

    @Slot(str)
    def append_log(self, text):
        self.log_view.appendPlainText(text)
        # Scroll to bottom
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    @Slot(list)
    def display_results(self, results):
        row, col = 0, 0
        max_cols = 3
        
        for cut in results:
            card = ResultCard(cut)
            self.results_grid.addWidget(card, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # Add a spacer to keep items at top
        self.results_grid.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), row + 1, 0)

    def on_pipeline_finished(self, success, report_path):
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if success:
            self.status_label.setText("Concluído! Veja os resultados.")
            self.switch_page(4) # Move to results page (was 3)
        else:
            self.status_label.setText("O processamento falhou. Verifique os logs.")

def main():
    # High DPI: definir antes de criar QApplication
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    app = QApplication(sys.argv)

    # Fonte com tamanho passado direto no construtor (evita QFont::setPointSize <= 0)
    app.setFont(QFont("Segoe UI", 10))
    
    window = ViralCutterApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()