# -*- coding: utf-8 -*-
# auto_list_ui.py

import sys
import os
import logging
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QFrame, QProgressBar, QMessageBox, QComboBox, QButtonGroup,
    QRadioButton, QGroupBox, QLineEdit, QGridLayout  # <--- ADICIONADO AQUI
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

# Local imports
from auto_list import YouTubeSearcher, save_to_list, REGIONS
from ui_styles import BLOOMBERG_THEME

logger = logging.getLogger("auto_list_ui")

class SearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, searcher, category_key, count):
        super().__init__()
        self.searcher = searcher
        self.category_key = category_key
        self.count = count
        
    def run(self):
        try:
            videos = self.searcher.search_trending_videos(self.category_key, max_results=self.count)
            self.finished.emit(videos)
        except Exception as e:
            self.error.emit(str(e))

class AutoListUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUTO_LIST_FINDER // BLOOMBERG_TERMINAL")
        self.setMinimumSize(1000, 750)
        
        self.searcher = None
        self.worker = None
        self._current_region = "BR"  # região ativa
        
        self.setStyleSheet(BLOOMBERG_THEME)
        self.init_ui()
        self._init_searcher()

    def _init_searcher(self, region: str = "BR"):
        """Cria (ou recria) o YouTubeSearcher com a região selecionada."""
        try:
            self.searcher = YouTubeSearcher(region=region)
            self._current_region = region
        except Exception as e:
            logger.error(f"Erro ao autenticar: {e}")
            self.searcher = None

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
        
        logo_label = QLabel("  AUTO_LIST_TERMINAL // NICHE_FINDER")
        
        self.timer_label = QLabel("")
        self._update_time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)
        
        top_bar_layout.addWidget(logo_label)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.timer_label)
        
        base_layout.addWidget(self.top_bar)

        # 2. Main Workspace
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(15, 15, 15, 15)
        workspace_layout.setSpacing(15)

        # ── Header ────────────────────────────────────────────────────────────
        header = QLabel("NICHE_EXPLORER // PROFITABLE_CONTENT_SEARCH")
        header.setObjectName("headerLabel")
        workspace_layout.addWidget(header)
        
        # ── Configuration Group ───────────────────────────────────────────────
        cfg_group = QGroupBox("SEARCH_PARAMETERS")
        cfg_layout = QGridLayout(cfg_group)
        cfg_layout.setSpacing(10)

        cfg_layout.addWidget(QLabel("TARGET_CHANNEL:"), 0, 0)
        
        region_selector = QHBoxLayout()
        self.btn_br = QRadioButton("BR_PORTUGUESE")
        self.btn_us = QRadioButton("US_ENGLISH")
        self.btn_br.setChecked(True)

        self.region_group = QButtonGroup(self)
        self.region_group.addButton(self.btn_br, 0)
        self.region_group.addButton(self.btn_us, 1)
        self.region_group.buttonClicked.connect(self._on_region_changed)

        region_selector.addWidget(self.btn_br)
        region_selector.addWidget(self.btn_us)
        region_selector.addStretch()
        cfg_layout.addLayout(region_selector, 0, 1)

        cfg_layout.addWidget(QLabel("VIDEO_COUNT:"), 1, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setValue(10)
        cfg_layout.addWidget(self.count_spin, 1, 1)
        
        workspace_layout.addWidget(cfg_group)

        # ── Tabela de nichos ──────────────────────────────────────────────────
        table_group = QGroupBox("PROFITABLE_NICHES_DATABASE")
        table_layout = QVBoxLayout(table_group)
        
        self.table = QTableWidget(len(YouTubeSearcher.CATEGORIES), 4)
        self.table.setHorizontalHeaderLabels(["ID", "NICHE_NAME", "PAYMENT_POTENTIAL", "VIRAL_VELOCITY"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._populate_table()
        table_layout.addWidget(self.table)
        
        workspace_layout.addWidget(table_group)
        
        # ── Execution ─────────────────────────────────────────────────────────
        self.search_btn = QPushButton("<GO> SCAN_AND_AUTO_APPEND_TO_LIST")
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.setMinimumHeight(60)
        self.search_btn.clicked.connect(self.start_search)
        workspace_layout.addWidget(self.search_btn)
        
        # ── Status ────────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(20)
        workspace_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("> SYSTEM_READY")
        self.status_label.setStyleSheet("color: #00FF00; font-weight: 900; font-size: 12px;")
        workspace_layout.addWidget(self.status_label)

        base_layout.addWidget(workspace)

    def _update_time(self):
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S  %d-%m-%Y")
        self.timer_label.setText(f"TERMINAL_LIVE: {now}  ")

    def _populate_table(self):
        """Preenche a tabela de nichos com cores de terminal."""
        self.table.setRowCount(0)
        for i, (key, val) in enumerate(YouTubeSearcher.CATEGORIES.items()):
            self.table.insertRow(i)
            
            id_item = QTableWidgetItem(key)
            id_item.setForeground(QColor("#FFB900"))
            self.table.setItem(i, 0, id_item)
            
            name_item = QTableWidgetItem(val['name'].upper())
            name_item.setForeground(QColor("#FFB900"))
            self.table.setItem(i, 1, name_item)
            
            pay_item = QTableWidgetItem(val['pay'].upper())
            if "VERY HIGH" in val['pay'].upper():
                pay_item.setForeground(QColor("#00FF00"))
            elif "HIGH" in val['pay'].upper():
                pay_item.setForeground(QColor("#00CC33"))
            else:
                pay_item.setForeground(QColor("#FFB900"))
            self.table.setItem(i, 2, pay_item)
            
            viral_item = QTableWidgetItem(val['viral'].upper())
            if "EXTREMELY" in val['viral'].upper():
                viral_item.setForeground(QColor("#FF0000"))
            elif "VERY HIGH" in val['viral'].upper():
                viral_item.setForeground(QColor("#FF8000"))
            else:
                viral_item.setForeground(QColor("#00FF00"))
            self.table.setItem(i, 3, viral_item)

    def _on_region_changed(self, btn):
        """Chamado quando o usuário troca de região."""
        new_region = "US" if self.region_group.id(btn) == 1 else "BR"
        if new_region == self._current_region:
            return
        self.status_label.setText(f"> INITIALIZING_CONNECTION: {REGIONS[new_region]['label']}...")
        self._init_searcher(new_region)
        if self.searcher:
            self.status_label.setText(f"> CONNECTION_STABLISHED: {REGIONS[new_region]['label']}")
        else:
            self.status_label.setText("> ERROR: CONNECTION_FAILED. CHECK_AUTH.")

    def start_search(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Aviso", "Selecione um nicho na tabela primeiro.")
            return
            
        category_key = self.table.item(self.table.currentRow(), 0).text()
        count = self.count_spin.value()
        
        if not self.searcher:
            try:
                self._init_searcher(self._current_region)
            except Exception as e:
                QMessageBox.critical(self, "Erro de Autenticação", f"Não foi possível conectar ao YouTube:\n{e}")
                return

        region_label = REGIONS[self._current_region]['label']
        cat_name = YouTubeSearcher.CATEGORIES[category_key]['name']

        self.search_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"> SCANNING_YOUTUBE: '{cat_name.upper()}' IN {region_label.upper()}...")
        
        self.worker = SearchWorker(self.searcher, category_key, count)
        self.worker.finished.connect(self.on_search_finished)
        self.worker.error.connect(self.on_search_error)
        self.worker.start()

    def on_search_finished(self, videos):
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if not videos:
            self.status_label.setText("> SCAN_RESULT: ZERO_MATCHES_FOUND.")
            return

        # Mostra preview dos títulos encontrados
        preview = "\n".join(
            f"• [{v.get('channel','')}] {v['title'][:60]}{'…' if len(v['title'])>60 else ''}"
            for v in videos
        )
        confirm = QMessageBox.question(
            self,
            "// CONFIRM_APPEND",
            f"DATA_RETRIEVED ({len(videos)} items):\n\n{preview}\n\nAPPEND TO list.txt?",
            QMessageBox.Yes | QMessageBox.No,
        )
        
        if confirm == QMessageBox.Yes:
            added_count = save_to_list(videos)
            if added_count > 0:
                self.status_label.setText(f"> IO_STATUS: {added_count} ENTRIES_WRITTEN_TO_DISK.")
                QMessageBox.information(self, "OK", f"{added_count} items added to list.")
            else:
                self.status_label.setText("> IO_STATUS: NO_NEW_ENTRIES (DUPLICATE_FILTERED).")
                QMessageBox.warning(self, "WARN", "Items already exist in database.")
        else:
            self.status_label.setText("> ACTION_ABORTED_BY_USER.")

    def on_search_error(self, err_msg):
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("> ERROR: SCAN_FAILED.")
        QMessageBox.critical(self, "ERROR", f"CRITICAL_FAILURE: {err_msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AutoListUI()
    window.show()
    sys.exit(app.exec())