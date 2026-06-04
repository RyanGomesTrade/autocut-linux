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
    QSizePolicy, QSpacerItem, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QRadioButton, QButtonGroup, QTabWidget
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QIcon, QFont, QPixmap, QColor

# Local imports
from ui_styles import BLOOMBERG_THEME
from ui_worker import PipelineWorker, DownloadWorker, BatchPipelineWorker
from cutter import EXPORT_PRESETS
from youtube_uploader import YouTubeUploader

class ResultCard(QFrame):
    """
    A card component to display a generated viral cut in Terminal Style.
    """
    def __init__(self, cut_data):
        super().__init__()
        self.setObjectName("resultCard")
        self.cut_data = cut_data
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        title = QLabel(f"ID: {self.cut_data.get('cut_index', 0):03d}")
        title.setStyleSheet("color: #FFB900; font-weight: 900; background-color: #1A1A1A; padding: 2px;")
        layout.addWidget(title)

        time_info = QLabel(f"DUR: {self.cut_data.get('duration', 0):.1f}s")
        time_info.setStyleSheet("color: #00FF00; font-size: 11px;")
        layout.addWidget(time_info)

        score = QLabel(f"SCORE: {self.cut_data.get('score', 0):.1f}")
        score.setStyleSheet("color: #00FF00; font-size: 11px;")
        layout.addWidget(score)

        open_btn = QPushButton("<OPEN>")
        open_btn.setObjectName("secondaryButton")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_file)
        layout.addWidget(open_btn)

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
        self.setWindowTitle("VIRAL_CUTTER // BLOOMBERG_TERMINAL_V2")
        self.setMinimumSize(1200, 800)
        
        # Application State
        self.worker = None
        self.uploader = YouTubeUploader()
        self.config = self._load_default_config()

        self.setStyleSheet(BLOOMBERG_THEME)
        self.init_ui()

    def _load_default_config(self):
        return {
            "input": "",
            "batch_list": None,
            "upload_youtube": False,
            "use_playwright": False,
            "youtube_profile_index": 0,
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
            "preset":              "auto_detect",
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
            "visual_filter": "none",
            "bg_music": None,
            "bg_music_volume": 0.15,
            "fade_duration": 0.5,
            "progress_bar": False,
            "auto_frame": False,
            "watermark_image":     None,
            "watermark_text":      None,
            "watermark_position":  "bottom_right",
            "watermark_opacity":   0.8,
            "watermark_scale":     1.0,
            "watermark_font_size": 40,
            "watermark_font_color": "white",
            "watermark_mode":      "auto", # auto, image, text, both
            "upload_interval_min": 0,      # 0 = imediato, >0 = espera entre posts
        }

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Base Layout (Vertical)
        base_layout = QVBoxLayout(central_widget)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(0)

        # 1. Top Blue Bar (Command Header)
        self.top_bar = QFrame()
        self.top_bar.setObjectName("commandHeader")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        
        logo_label = QLabel("  VIRAL_CUTTER_PRO // CMD_CENTER")
        
        self.timer_label = QLabel("")
        self._update_time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)
        
        top_bar_layout.addWidget(logo_label)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.timer_label)
        
        base_layout.addWidget(self.top_bar)

        # 2. Main Workspace (Horizontal: Sidebar + Content)
        workspace = QWidget()
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # 2.1 Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        nav_label = QLabel("  TERMINAL_FUNCTIONS")
        nav_label.setObjectName("navLabel")
        sidebar_layout.addWidget(nav_label)

        self.nav_btns = []
        sidebar_layout.addWidget(self._create_nav_btn(" <1> DASHBOARD_IO", 0))
        sidebar_layout.addWidget(self._create_nav_btn(" <2> BATCH_QUEUE", 1))
        sidebar_layout.addWidget(self._create_nav_btn(" <3> SYSTEM_PARAMS", 2))
        sidebar_layout.addWidget(self._create_nav_btn(" <4> REALTIME_LOG", 3))
        sidebar_layout.addWidget(self._create_nav_btn(" <5> OUTPUT_VAULT", 4))
        
        sidebar_layout.addStretch()
        
        # System Status Box
        status_box = QFrame()
        status_box.setObjectName("statusBox")
        status_layout = QVBoxLayout(status_box)
        
        status_header = QLabel("NETWORK_STATUS")
        status_header.setObjectName("statusHeader")
        status_layout.addWidget(status_header)
        
        self.engine_status = QLabel("CONNECTING...")
        self.engine_status.setObjectName("engineStatus")
        status_layout.addWidget(self.engine_status)
        
        sidebar_layout.addWidget(status_box)
        workspace_layout.addWidget(self.sidebar)

        # 2.2 Content Stack
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        
        self._setup_dashboard_page()
        self._setup_batch_page()
        self._setup_settings_page()
        self._setup_progress_page()
        self._setup_results_page()
        
        workspace_layout.addWidget(self.content_stack)
        base_layout.addWidget(workspace)
        
        # Finalize
        self.switch_page(0)
        self.check_engines()

    def _update_time(self):
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S  %d-%m-%Y")
        self.timer_label.setText(f"TERMINAL_LIVE: {now}  ")

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
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("DASHBOARD_FEED // SYSTEM_INPUT")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # Main Entry Grid (More dense)
        grid = QGridLayout()
        grid.setSpacing(5)

        # Row 0: Local Input
        grid.addWidget(QLabel("LOCAL_SOURCE_PATH:"), 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("C:/MEDIA/RAW_VIDEO.MP4")
        self.input_edit.textChanged.connect(lambda t: self._update_config("input", t))
        grid.addWidget(self.input_edit, 0, 1)
        
        browse_btn = QPushButton("[BROWSE]")
        browse_btn.setObjectName("secondaryButton")
        browse_btn.clicked.connect(self.browse_input)
        grid.addWidget(browse_btn, 0, 2)

        # Row 1: Remote URL
        grid.addWidget(QLabel("REMOTE_YOUTUBE_URL:"), 1, 0)
        self.yt_url_edit = QLineEdit()
        self.yt_url_edit.setPlaceholderText("HTTPS://YOUTUBE.COM/WATCH?V=...")
        grid.addWidget(self.yt_url_edit, 1, 1)
        
        self.yt_dl_btn = QPushButton("[DL_REMOTE]")
        self.yt_dl_btn.setObjectName("secondaryButton")
        self.yt_dl_btn.clicked.connect(self.start_youtube_download)
        grid.addWidget(self.yt_dl_btn, 1, 2)

        self.yt_progress = QProgressBar()
        self.yt_progress.setVisible(False)
        self.yt_progress.setFixedHeight(10)
        grid.addWidget(self.yt_progress, 1, 3)

        # Row 2: Output Dir
        grid.addWidget(QLabel("STORAGE_TARGET:"), 2, 0)
        self.output_edit = QLineEdit()
        self.output_edit.setText(self.config["output"])
        self.output_edit.textChanged.connect(lambda t: self._update_config("output", t))
        grid.addWidget(self.output_edit, 2, 1)
        
        out_browse_btn = QPushButton("[SET_PATH]")
        out_browse_btn.setObjectName("secondaryButton")
        out_browse_btn.clicked.connect(self.browse_output)
        grid.addWidget(out_browse_btn, 2, 2)

        layout.addLayout(grid)

        # Quick Config
        quick_cfg = QHBoxLayout()
        
        p_group = QGroupBox("PIPELINE_EXEC_PARAMS")
        p_layout = QGridLayout(p_group)
        p_layout.setSpacing(10)

        p_layout.addWidget(QLabel("EXPORT_PRESET:"), 0, 0)
        self.combo_preset = QComboBox()
        presets = ["auto_detect", "shorts_blur", "podcast_split", "tiktok", "reels", "shorts", "landscape", "square", "social_frame"]
        for p in presets: self.combo_preset.addItem(p.upper(), p)
        self.combo_preset.setCurrentText(self.config.get("preset", "auto_detect").upper())
        self.combo_preset.currentIndexChanged.connect(lambda i: self._update_config("preset", self.combo_preset.itemData(i)))
        p_layout.addWidget(self.combo_preset, 0, 1)

        p_layout.addWidget(QLabel("SUBTITLE_MODE:"), 1, 0)
        self.combo_subs = QComboBox()
        self.combo_subs.addItems(["VIRAL_HIGH", "BURN_IN", "SOFT_RAW", "DISABLED"])
        style_map = {"high_impact": 0, "hardcoded": 1, "soft": 2, "none": 3}
        self.combo_subs.setCurrentIndex(style_map.get(self.config["subtitle_style"], 0))
        self.combo_subs.currentIndexChanged.connect(self.update_sub_style)
        p_layout.addWidget(self.combo_subs, 1, 1)
        
        quick_cfg.addWidget(p_group)

        u_group = QGroupBox("UPLOAD_GATEWAY")
        u_layout = QVBoxLayout(u_group)
        
        self.check_upload = QCheckBox("AUTO_POST_ON_COMPLETE")
        self.check_upload.setChecked(self.config.get("upload_youtube", False))
        self.check_upload.toggled.connect(lambda b: self._update_config("upload_youtube", b))
        u_layout.addWidget(self.check_upload)

        self.combo_yt_profile_dash = QComboBox()
        self._refresh_yt_profiles()
        self.combo_yt_profile_dash.currentIndexChanged.connect(self._on_yt_profile_changed)
        u_layout.addWidget(self.combo_yt_profile_dash)
        
        # Method selector in upload group
        m_layout = QHBoxLayout()
        self.radio_api = QRadioButton("API_V3")
        self.radio_pw = QRadioButton("PW_BOT")
        self.method_group = QButtonGroup(self)
        self.method_group.addButton(self.radio_api, 0)
        self.method_group.addButton(self.radio_pw, 1)
        if self.config.get("use_playwright"): self.radio_pw.setChecked(True)
        else: self.radio_api.setChecked(True)
        self.method_group.buttonClicked.connect(self._on_upload_method_changed)
        m_layout.addWidget(self.radio_api)
        m_layout.addWidget(self.radio_pw)
        u_layout.addLayout(m_layout)
        
        quick_cfg.addWidget(u_group)
        layout.addLayout(quick_cfg)

        layout.addStretch()

        # Execute Button
        self.start_btn = QPushButton("<GO> EXECUTE_TERMINAL_PIPELINE")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setMinimumHeight(80)
        self.start_btn.clicked.connect(self.start_pipeline)
        layout.addWidget(self.start_btn)

        self.content_stack.addWidget(page)

    def _setup_batch_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("BATCH_PROCESSOR // QUEUE_CONTROL")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # Toolbar
        tbar = QHBoxLayout()
        tbar.setSpacing(5)
        
        self.add_row_btn = QPushButton("[ADD_URL]")
        self.add_row_btn.setObjectName("secondaryButton")
        self.add_row_btn.clicked.connect(lambda: self.add_batch_row())
        
        self.import_btn = QPushButton("[IMPORT_LIST]")
        self.import_btn.setObjectName("secondaryButton")
        self.import_btn.clicked.connect(self.import_batch_list)
        
        self.save_btn = QPushButton("[EXPORT_LIST]")
        self.save_btn.setObjectName("secondaryButton")
        self.save_btn.clicked.connect(self.save_batch_list)

        self.clear_btn = QPushButton("[PURGE_ALL]")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.setStyleSheet("color: #FF0000; border-color: #FF0000;")
        self.clear_btn.clicked.connect(lambda: self.batch_table.setRowCount(0))

        tbar.addWidget(self.add_row_btn)
        tbar.addWidget(self.import_btn)
        tbar.addWidget(self.save_btn)
        tbar.addStretch()
        tbar.addWidget(self.clear_btn)
        layout.addLayout(tbar)

        # Table
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels(["SOURCE_URL", "PRESET_ID", "TITLE_TAG", "CMD"])
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.batch_table.verticalHeader().setVisible(False)
        layout.addWidget(self.batch_table)

        # Batch Global Config
        b_cfg = QGroupBox("GLOBAL_BATCH_PARAMETERS")
        bg_layout = QGridLayout(b_cfg)
        
        bg_layout.addWidget(QLabel("ACTIVE_CHANNEL:"), 0, 0)
        self.combo_yt_profile = QComboBox()
        self._refresh_yt_profiles()
        self.combo_yt_profile.currentIndexChanged.connect(self._on_yt_profile_changed)
        bg_layout.addWidget(self.combo_yt_profile, 0, 1)

        bg_layout.addWidget(QLabel("INTERVAL_HRS:"), 0, 2)
        self.schedule_spin = QSpinBox()
        self.schedule_spin.setRange(0, 72)
        self.schedule_spin.setValue(self.config.get("schedule_interval", 0))
        self.schedule_spin.valueChanged.connect(lambda v: self._update_config("schedule_interval", v))
        bg_layout.addWidget(self.schedule_spin, 0, 3)

        # New Upload Options for Batch
        self.check_upload_batch = QCheckBox("AUTO_POST_ON_COMPLETE")
        self.check_upload_batch.setChecked(self.config.get("upload_youtube", False))
        self.check_upload_batch.toggled.connect(lambda b: self._update_config("upload_youtube", b))
        bg_layout.addWidget(self.check_upload_batch, 1, 0, 1, 2)

        # Method selector for Batch
        m_layout = QHBoxLayout()
        self.radio_api_batch = QRadioButton("API_V3")
        self.radio_pw_batch = QRadioButton("PW_BOT")
        self.method_group_batch = QButtonGroup(self)
        self.method_group_batch.addButton(self.radio_api_batch, 0)
        self.method_group_batch.addButton(self.radio_pw_batch, 1)
        if self.config.get("use_playwright"): self.radio_pw_batch.setChecked(True)
        else: self.radio_api_batch.setChecked(True)
        self.method_group_batch.buttonClicked.connect(self._on_upload_method_changed)
        m_layout.addWidget(self.radio_api_batch)
        m_layout.addWidget(self.radio_pw_batch)
        bg_layout.addLayout(m_layout, 1, 2, 1, 2)

        layout.addWidget(b_cfg)

        # Channel Ops
        ops_group = QGroupBox("CHANNEL_OPERATIONS")
        ops_layout = QHBoxLayout(ops_group)
        
        btn_add = QPushButton("[NEW_CHNL]")
        btn_add.setObjectName("secondaryButton")
        btn_add.clicked.connect(self.show_add_profile_dialog)
        
        btn_ren = QPushButton("[RENAME]")
        btn_ren.setObjectName("secondaryButton")
        btn_ren.clicked.connect(self.rename_current_profile)
        
        btn_rm = QPushButton("[DELETE]")
        btn_rm.setObjectName("secondaryButton")
        btn_rm.clicked.connect(self.remove_current_profile)
        
        btn_login = QPushButton("[PW_LOGIN]")
        btn_login.setObjectName("secondaryButton")
        btn_login.clicked.connect(self.login_via_playwright)
        
        btn_reset = QPushButton("[PW_RESET]")
        btn_reset.setObjectName("secondaryButton")
        btn_reset.clicked.connect(self.reset_playwright_session)
        
        ops_layout.addWidget(btn_add)
        ops_layout.addWidget(btn_ren)
        ops_layout.addWidget(btn_rm)
        ops_layout.addStretch()
        ops_layout.addWidget(btn_login)
        ops_layout.addWidget(btn_reset)
        layout.addWidget(ops_group)

        # Execute Batch
        self.start_batch_btn = QPushButton("<GO> EXECUTE_BATCH_PIPELINE")
        self.start_batch_btn.setObjectName("primaryButton")
        self.start_batch_btn.setMinimumHeight(60)
        self.start_batch_btn.clicked.connect(self.start_batch_pipeline)
        layout.addWidget(self.start_batch_btn)

        self.content_stack.addWidget(page)

    def _refresh_yt_profiles(self):
        """Atualiza os comboboxes de perfis do YouTube."""
        # Salva o índice atual se existir
        curr_idx = self.config.get("youtube_profile_index", 0)
        
        # Atualiza Combo do Dashboard
        if hasattr(self, 'combo_yt_profile_dash'):
            self.combo_yt_profile_dash.clear()
            for p in self.uploader.profiles:
                self.combo_yt_profile_dash.addItem(p["name"])
            self.combo_yt_profile_dash.setCurrentIndex(curr_idx)

        # Atualiza Combo do Gerenciar Lote
        if hasattr(self, 'combo_yt_profile'):
            self.combo_yt_profile.clear()
            for p in self.uploader.profiles:
                self.combo_yt_profile.addItem(p["name"])
            self.combo_yt_profile.setCurrentIndex(curr_idx)

    def login_via_playwright(self):
        """Abre o navegador para o usuário logar no YouTube Studio."""
        from playwright_uploader import PlaywrightUploader
        
        # Obtém o nome do perfil selecionado para separar as sessões
        profile_index = self.combo_yt_profile.currentIndex()
        profile_name = "default"
        if 0 <= profile_index < len(self.uploader.profiles):
            profile_name = self.uploader.profiles[profile_index]["name"]

        try:
            uploader = PlaywrightUploader(profile_name=profile_name)
            uploader.login()
            uploader.close()
            QMessageBox.information(self, "playwright", f"Session for '{profile_name}' saved OK.")
        except Exception as e:
            QMessageBox.critical(self, "ERROR: playwright", f"Could not open browser for '{profile_name}':\n{e}")

    def reset_playwright_session(self):
        """Reseta a sessão do Playwright para o canal selecionado."""
        from playwright_uploader import PlaywrightUploader
        idx = self.combo_yt_profile.currentIndex()
        if idx < 0: return
        
        profile_name = self.uploader.profiles[idx]["name"]
        confirm = QMessageBox.question(
            self, "// confirm_reset",
            f"Reset playwright session for '{profile_name}'?\nYou will need to login again.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            try:
                uploader = PlaywrightUploader(profile_name=profile_name)
                if uploader.reset_session():
                    QMessageBox.information(self, "OK", f"Session for '{profile_name}' reset. Login again to re-authenticate.")
                else:
                    QMessageBox.warning(self, "WARN", "No session found for this channel.")
            except Exception as e:
                QMessageBox.critical(self, "ERROR", f"Failed to reset session: {e}")

    def show_add_profile_dialog(self):
        """Mostra um diálogo simples para adicionar um novo perfil do YouTube."""
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("// new_channel")
        layout = QFormLayout(dialog)
        
        next_idx = len(self.uploader.profiles) + 1
        name_edit = QLineEdit(f"channel_{next_idx}")
        
        secrets_row = QHBoxLayout()
        secrets_edit = QLineEdit("client_secrets.json")
        browse_secrets_btn = QPushButton("[...]")
        browse_secrets_btn.setFixedWidth(40)
        browse_secrets_btn.clicked.connect(lambda: self._browse_for_file(secrets_edit, "Segredos do Google (JSON)", "*.json"))
        secrets_row.addWidget(secrets_edit)
        secrets_row.addWidget(browse_secrets_btn)
        
        token_edit = QLineEdit(f"token_canal_{next_idx}.pickle")
        
        layout.addRow("--name:", name_edit)
        layout.addRow("--secrets:", secrets_row)
        layout.addRow("--token:", token_edit)
        
        info_label = QLabel("> token name depends on which client_secrets.json you pick.")
        info_label.setStyleSheet("color: #00CC33; font-size: 11px; font-family: 'Consolas',monospace;")
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

    def rename_current_profile(self):
        """Abre um diálogo para renomear o perfil selecionado."""
        idx = self.combo_yt_profile.currentIndex()
        if idx < 0: return
        
        old_name = self.uploader.profiles[idx]["name"]
        
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "// rename_channel", 
            f"new name for '{old_name}':",
            QLineEdit.Normal, old_name
        )
        
        if ok and new_name.strip() and new_name != old_name:
            if self.uploader.rename_profile(idx, new_name.strip()):
                self._refresh_yt_profiles()
                QMessageBox.information(self, "Sucesso", f"Canal renomeado para '{new_name.strip()}' com sucesso.")

    def remove_current_profile(self):
        """Remove o perfil selecionado atualmente."""
        idx = self.combo_yt_profile.currentIndex()
        if idx < 0: return
        
        profile_name = self.uploader.profiles[idx]["name"]
        confirm = QMessageBox.question(
            self, "// confirm_remove",
            f"Remove channel '{profile_name}'?\nThis will also delete the local token file.",
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

    def add_batch_row(self, url="", preset="shorts_blur", title=""):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        
        # URL
        url_edit = QLineEdit(url)
        url_edit.setPlaceholderText("HTTPS://YOUTUBE.COM/WATCH?V=...")
        url_edit.setStyleSheet("border: 1px solid #333333; background: #000000; color: #00FF00;")
        self.batch_table.setCellWidget(row, 0, url_edit)
        
        # Preset
        preset_combo = QComboBox()
        preset_combo.addItems(list(EXPORT_PRESETS.keys()))
        preset_combo.setCurrentText(preset)
        self.batch_table.setCellWidget(row, 1, preset_combo)
        
        # Title
        title_edit = QLineEdit(title)
        title_edit.setPlaceholderText("OPTIONAL_PREFIX")
        title_edit.setStyleSheet("border: 1px solid #333333; background: #000000; color: #00FF00;")
        self.batch_table.setCellWidget(row, 2, title_edit)
        
        # Remove Btn
        remove_btn = QPushButton("[X]")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet("color: #FF0000; font-weight: 900; border: 1px solid #333333;")
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
            self.status_label.setText("> ERROR: no jobs in queue.")
            return

        self.config["batch_jobs"] = jobs
        
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("> initializing batch pipeline ...")
        self.switch_page(3)
        
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
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("SYSTEM_PARAMETERS // GLOBAL_CONFIG")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        # 1. AI & Transcription
        ai_group = QGroupBox("AI_ENGINE_CONFIG")
        ai_layout = QGridLayout(ai_group)
        
        ai_layout.addWidget(QLabel("WHISPER_MODEL:"), 0, 0)
        self.combo_w_model = QComboBox()
        self.combo_w_model.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        self.combo_w_model.setCurrentText(self.config["whisper_model"])
        self.combo_w_model.currentTextChanged.connect(lambda t: self._update_config("whisper_model", t))
        ai_layout.addWidget(self.combo_w_model, 0, 1)

        ai_layout.addWidget(QLabel("COMPUTE_DEVICE:"), 0, 2)
        self.combo_device = QComboBox()
        self.combo_device.addItems(["cpu", "cuda"])
        self.combo_device.currentTextChanged.connect(lambda t: self._update_config("device", t))
        ai_layout.addWidget(self.combo_device, 0, 3)

        ai_layout.addWidget(QLabel("ANALYSIS_MODE:"), 1, 0)
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Ollama (IA)", "Heurística (FAST)"])
        self.combo_engine.setCurrentIndex(0 if self.config["analysis_engine"] == "ollama" else 1)
        self.combo_engine.currentIndexChanged.connect(lambda i: self._update_config("analysis_engine", "ollama" if i == 0 else "heuristic"))
        ai_layout.addWidget(self.combo_engine, 1, 1)

        ai_layout.addWidget(QLabel("OLLAMA_MODEL:"), 1, 2)
        self.edit_o_model = QLineEdit(self.config["model"])
        self.edit_o_model.textChanged.connect(lambda t: self._update_config("model", t))
        ai_layout.addWidget(self.edit_o_model, 1, 3)
        
        layout.addWidget(ai_group)

        # 2. Pipeline Params
        pipe_group = QGroupBox("PIPELINE_CONSTRAINTS")
        p_layout = QGridLayout(pipe_group)
        
        p_layout.addWidget(QLabel("MAX_CUTS:"), 0, 0)
        self.spin_topn = QSpinBox()
        self.spin_topn.setRange(1, 100)
        self.spin_topn.setValue(self.config["top_n"])
        self.spin_topn.valueChanged.connect(lambda v: self._update_config("top_n", v))
        p_layout.addWidget(self.spin_topn, 0, 1)

        p_layout.addWidget(QLabel("MIN_DUR_SEC:"), 0, 2)
        self.spin_min_d = QSpinBox()
        self.spin_min_d.setRange(5, 300)
        self.spin_min_d.setValue(int(self.config["min_duration"]))
        self.spin_min_d.valueChanged.connect(lambda v: self._update_config("min_duration", float(v)))
        p_layout.addWidget(self.spin_min_d, 0, 3)

        p_layout.addWidget(QLabel("MAX_DUR_SEC:"), 1, 0)
        self.spin_max_d = QSpinBox()
        self.spin_max_d.setRange(5, 600)
        self.spin_max_d.setValue(int(self.config["max_duration"]))
        self.spin_max_d.valueChanged.connect(lambda v: self._update_config("max_duration", float(v)))
        p_layout.addWidget(self.spin_max_d, 1, 1)

        self.check_silence = QCheckBox("SILENCE_DETECTION_FILTER")
        self.check_silence.setChecked(not self.config["no_silence_detect"])
        self.check_silence.toggled.connect(lambda b: self._update_config("no_silence_detect", not b))
        p_layout.addWidget(self.check_silence, 1, 2, 1, 2)
        
        layout.addWidget(pipe_group)

        # 3. Visual FX
        fx_group = QGroupBox("VISUAL_EFFECTS_ENGINE")
        fx_layout = QGridLayout(fx_group)

        fx_layout.addWidget(QLabel("COLOR_FILTER:"), 0, 0)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["none", "vibrant", "cinematic", "warm"])
        self.combo_filter.currentTextChanged.connect(lambda t: self._update_config("visual_filter", t))
        fx_layout.addWidget(self.combo_filter, 0, 1)

        fx_layout.addWidget(QLabel("BG_MUSIC_PATH:"), 1, 0)
        music_row = QHBoxLayout()
        self.music_edit = QLineEdit()
        self.music_edit.setText(self.config.get("bg_music") or "")
        self.music_edit.textChanged.connect(lambda t: self._update_config("bg_music", t))
        btn_music = QPushButton("[...]")
        btn_music.setFixedWidth(40)
        btn_music.clicked.connect(self.browse_music)
        music_row.addWidget(self.music_edit)
        music_row.addWidget(btn_music)
        fx_layout.addLayout(music_row, 1, 1)

        fx_layout.addWidget(QLabel("MUSIC_VOL_%:"), 1, 2)
        self.spin_volume = QSpinBox()
        self.spin_volume.setRange(0, 100)
        self.spin_volume.setValue(int(self.config["bg_music_volume"] * 100))
        self.spin_volume.valueChanged.connect(lambda v: self._update_config("bg_music_volume", v / 100.0))
        fx_layout.addWidget(self.spin_volume, 1, 3)

        self.check_progress = QCheckBox("RENDER_PROGRESS_BAR_OVERLAY")
        self.check_progress.setChecked(self.config["progress_bar"])
        self.check_progress.toggled.connect(lambda b: self._update_config("progress_bar", b))
        fx_layout.addWidget(self.check_progress, 2, 0, 1, 2)

        self.check_autoframe = QCheckBox("ENABLE_AI_FACE_TRACKING")
        self.check_autoframe.setChecked(self.config["auto_frame"])
        self.check_autoframe.toggled.connect(lambda b: self._update_config("auto_frame", b))
        fx_layout.addWidget(self.check_autoframe, 2, 2, 1, 2)

        layout.addWidget(fx_group)

        # 4. Watermark
        wm_group = QGroupBox("WATERMARK_OVERLAY_CONTROL")
        wm_layout = QGridLayout(wm_group)

        wm_layout.addWidget(QLabel("MODO_MARCA:"), 0, 0)
        self.combo_wm_mode = QComboBox()
        self.combo_wm_mode.addItems(["AUTO (Detectar)", "APENAS_IMAGEM", "APENAS_TEXTO", "AMBOS"])
        mode_map = {"auto": 0, "image": 1, "text": 2, "both": 3}
        self.combo_wm_mode.setCurrentIndex(mode_map.get(self.config.get("watermark_mode", "auto"), 0))
        self.combo_wm_mode.currentIndexChanged.connect(self._on_wm_mode_changed)
        wm_layout.addWidget(self.combo_wm_mode, 0, 1)

        wm_layout.addWidget(QLabel("LOGO_PATH:"), 1, 0)
        wm_row = QHBoxLayout()
        self.wm_image_edit = QLineEdit()
        self.wm_image_edit.setText(self.config.get("watermark_image") or "")
        self.wm_image_edit.textChanged.connect(lambda t: self._update_config("watermark_image", t if t.strip() else None))
        btn_wm = QPushButton("[...]")
        btn_wm.setFixedWidth(40)
        btn_wm.clicked.connect(self.browse_watermark_image)
        wm_row.addWidget(self.wm_image_edit)
        wm_row.addWidget(btn_wm)
        wm_layout.addLayout(wm_row, 1, 1)

        wm_layout.addWidget(QLabel("BRAND_TEXT:"), 1, 2)
        self.wm_text_edit = QLineEdit()
        self.wm_text_edit.setText(self.config.get("watermark_text") or "")
        self.wm_text_edit.textChanged.connect(lambda t: self._update_config("watermark_text", t if t.strip() else None))
        wm_layout.addWidget(self.wm_text_edit, 1, 3)

        wm_layout.addWidget(QLabel("WM_POSITION:"), 2, 0)
        self.combo_wm_pos = QComboBox()
        wm_positions = ["bottom_right", "bottom_left", "top_right", "top_left", "bottom_center", "top_center", "center"]
        for pos in wm_positions: self.combo_wm_pos.addItem(pos.upper(), pos)
        self.combo_wm_pos.setCurrentText(self.config.get("watermark_position", "bottom_right").upper())
        self.combo_wm_pos.currentIndexChanged.connect(lambda i: self._update_config("watermark_position", self.combo_wm_pos.itemData(i)))
        wm_layout.addWidget(self.combo_wm_pos, 2, 1)

        wm_layout.addWidget(QLabel("OPACITY_%:"), 2, 2)
        self.spin_wm_opacity = QSpinBox()
        self.spin_wm_opacity.setRange(10, 100)
        self.spin_wm_opacity.setValue(int(self.config.get("watermark_opacity", 0.8) * 100))
        self.spin_wm_opacity.valueChanged.connect(lambda v: self._update_config("watermark_opacity", v / 100.0))
        wm_layout.addWidget(self.spin_wm_opacity, 2, 3)

        # Novas opções de texto
        wm_layout.addWidget(QLabel("FONTE_TAM:"), 3, 0)
        self.spin_wm_font_size = QSpinBox()
        self.spin_wm_font_size.setRange(10, 200)
        self.spin_wm_font_size.setValue(self.config.get("watermark_font_size", 40))
        self.spin_wm_font_size.valueChanged.connect(lambda v: self._update_config("watermark_font_size", v))
        wm_layout.addWidget(self.spin_wm_font_size, 3, 1)

        wm_layout.addWidget(QLabel("COR_FONTE:"), 3, 2)
        self.wm_color_edit = QLineEdit()
        self.wm_color_edit.setText(self.config.get("watermark_font_color", "white"))
        self.wm_color_edit.textChanged.connect(lambda t: self._update_config("watermark_font_color", t))
        wm_layout.addWidget(self.wm_color_edit, 3, 3)

        wm_layout.addWidget(self.wm_color_edit, 3, 3)

        layout.addWidget(wm_group)

        # 5. Advanced Upload
        up_group = QGroupBox("ADVANCED_POST_ENGINE")
        up_layout = QGridLayout(up_group)

        up_layout.addWidget(QLabel("UPLOAD_INTERVAL (min):"), 0, 0)
        self.spin_up_interval = QSpinBox()
        self.spin_up_interval.setRange(0, 1440) # Até 24h
        self.spin_up_interval.setValue(self.config.get("upload_interval_min", 0))
        self.spin_up_interval.setSuffix(" min")
        self.spin_up_interval.valueChanged.connect(lambda v: self._update_config("upload_interval_min", v))
        up_layout.addWidget(self.spin_up_interval, 0, 1)
        
        up_layout.addWidget(QLabel("INFO: 60 min = 1 post/hora"), 0, 2)

        layout.addWidget(up_group)

        layout.addStretch()
        
        scroll.setWidget(container)
        self.content_stack.addWidget(scroll)

    def _setup_progress_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("REALTIME_LOG // PROCESS_STDOUT")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        status_bar = QHBoxLayout()
        self.status_label = QLabel("> SYSTEM_IDLE")
        self.status_label.setStyleSheet("color: #00FF00; font-weight: 900;")
        status_bar.addWidget(self.status_label)
        status_bar.addStretch()
        layout.addLayout(status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #050505; border: 1px solid #1A1A1A; color: #00FF00; font-size: 11px;")
        layout.addWidget(self.log_view)

        self.content_stack.addWidget(page)

    def _setup_results_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel("OUTPUT_VAULT // GENERATED_ASSETS")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        
        self.results_container = QWidget()
        self.results_grid = QGridLayout(self.results_container)
        self.results_grid.setSpacing(10)
        self.results_scroll.setWidget(self.results_container)
        layout.addWidget(self.results_scroll)

        btn_row = QHBoxLayout()
        open_folder_btn = QPushButton("[OPEN_OUTPUT_DIR]")
        open_folder_btn.setObjectName("secondaryButton")
        open_folder_btn.clicked.connect(self.open_output_folder)
        
        btn_row.addStretch()
        btn_row.addWidget(open_folder_btn)
        layout.addLayout(btn_row)

        self.content_stack.addWidget(page)

    # --- Slots and Logic ---

    def _update_config(self, key, value):
        self.config[key] = value
        
        # Sync UI if needed
        if key == "upload_youtube":
            if hasattr(self, 'check_upload'):
                self.check_upload.blockSignals(True)
                self.check_upload.setChecked(value)
                self.check_upload.blockSignals(False)
            if hasattr(self, 'check_upload_batch'):
                self.check_upload_batch.blockSignals(True)
                self.check_upload_batch.setChecked(value)
                self.check_upload_batch.blockSignals(False)

    def _on_yt_profile_changed(self, index):
        """Chamado quando o usuário troca o canal (perfil) do YouTube."""
        if index < 0 or index >= len(self.uploader.profiles):
            return
            
        self._update_config("youtube_profile_index", index)
        
        # Sincroniza os dois menus (Dashboard e Gerenciar Lote)
        if hasattr(self, 'combo_yt_profile_dash') and self.combo_yt_profile_dash.currentIndex() != index:
            self.combo_yt_profile_dash.blockSignals(True)
            self.combo_yt_profile_dash.setCurrentIndex(index)
            self.combo_yt_profile_dash.blockSignals(False)
            
        if hasattr(self, 'combo_yt_profile') and self.combo_yt_profile.currentIndex() != index:
            self.combo_yt_profile.blockSignals(True)
            self.combo_yt_profile.setCurrentIndex(index)
            self.combo_yt_profile.blockSignals(False)
            
        logger.info(f"Perfil do YouTube alterado para: {self.uploader.profiles[index]['name']}")

    def _on_upload_method_changed(self, btn):
        """Chamado quando o usuário troca entre API e Playwright."""
        # Se for ID 1, é Playwright. Se for 0, é API.
        # Tenta pegar de qualquer um dos grupos
        if hasattr(self, 'method_group') and btn in self.method_group.buttons():
            use_pw = (self.method_group.id(btn) == 1)
        elif hasattr(self, 'method_group_batch') and btn in self.method_group_batch.buttons():
            use_pw = (self.method_group_batch.id(btn) == 1)
        else:
            return

        self.config["use_playwright"] = use_pw
        
        # Sincroniza os estados na UI
        if hasattr(self, 'radio_pw'): self.radio_pw.setChecked(use_pw)
        if hasattr(self, 'radio_api'): self.radio_api.setChecked(not use_pw)
        if hasattr(self, 'radio_pw_batch'): self.radio_pw_batch.setChecked(use_pw)
        if hasattr(self, 'radio_api_batch'): self.radio_api_batch.setChecked(not use_pw)
        
        logger.info(f"Método de upload alterado para: {'Playwright' if use_pw else 'API'}")

    def _on_wm_mode_changed(self, index):
        modes = ["auto", "image", "text", "both"]
        self._update_config("watermark_mode", modes[index])

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
            pkl_path = os.path.normpath(os.path.join(self.config["output"], "transcript.pkl"))
            if os.path.exists(pkl_path):
                self.config["skip_transcription"] = pkl_path
                self.append_log(f"> cache found: {pkl_path}")
            else:
                if hasattr(self, 'status_label'):
                    self.status_label.setText("> WARN: transcript.pkl not found.")
                self.append_log(f"> WARN: no cache at {self.config['output']}")
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
            self.status_label.setText(f"> download OK: {os.path.basename(file_path)}")
        else:
            self.status_label.setText("> ERROR: yt-dlp download failed.")

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
                self.engine_status.setText("$ ollama  [ONLINE]")
                self.engine_status.setStyleSheet("font-size: 11px; color: #00FF41; font-family: 'Consolas',monospace;")
            else:
                self.engine_status.setText("$ ollama  [OFFLINE]")
                self.engine_status.setStyleSheet("font-size: 11px; color: #FF4444; font-family: 'Consolas',monospace;")

        self._engine_checker = _OllamaChecker()
        self._engine_checker.done.connect(_apply)
        self._engine_checker.start()

    def start_pipeline(self):
        if not self.config["input"] or not os.path.exists(self.config["input"]):
            self.status_label.setText("> ERROR: invalid input file path.")
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
        self.status_label.setText("> initializing pipeline ...")
        self.switch_page(3)
        
        # Clear results from previous run (itemAt can return spacers with no widget)
        for i in reversed(range(self.results_grid.count())):
            item = self.results_grid.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

        # Ajusta marcas d'água baseado no modo selecionado
        final_config = dict(self.config)
        mode = final_config.get("watermark_mode", "auto")
        if mode == "image":
            final_config["watermark_text"] = None
        elif mode == "text":
            final_config["watermark_image"] = None
        elif mode == "auto":
            # Mantém original
            pass

        # Create and start worker
        if is_batch:
            self.worker = BatchPipelineWorker(final_config)
        else:
            self.worker = PipelineWorker(final_config)
            
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
            self.status_label.setText("> process complete. check output/ ...")
            self.switch_page(4)
        else:
            self.status_label.setText("> ERROR: process failed. check logs ...")

def main():
    # High DPI
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    app = QApplication(sys.argv)

    # Use Monospace as base font
    app.setFont(QFont("Consolas", 10))
    
    window = ViralCutterApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()