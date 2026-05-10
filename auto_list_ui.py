# -*- coding: utf-8 -*-
# auto_list_ui.py

import sys
import os
import logging
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QFrame, QProgressBar, QMessageBox, QComboBox, QButtonGroup,
    QRadioButton, QGroupBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

# Local imports
from auto_list import YouTubeSearcher, save_to_list, REGIONS
from ui_styles import APPLE_MINIMAL_THEME

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
        self.setWindowTitle("YouTube Auto List - Viral Cutter")
        self.setMinimumSize(860, 680)
        
        self.searcher = None
        self.worker = None
        self._current_region = "BR"  # região ativa
        
        self.init_ui()
        self.setStyleSheet(APPLE_MINIMAL_THEME)
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
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # ── Header ────────────────────────────────────────────────────────────
        header = QLabel("Explorar Nichos Lucrativos")
        header.setObjectName("headerLabel")
        layout.addWidget(header)
        
        desc = QLabel("Selecione o canal de destino, o nicho e a quantidade de vídeos para buscar.")
        desc.setStyleSheet("color: #86868B; font-size: 14px;")
        layout.addWidget(desc)

        # ── Seletor de região ─────────────────────────────────────────────────
        region_card = QFrame()
        region_card.setObjectName("resultCard")
        region_layout = QHBoxLayout(region_card)
        region_layout.setContentsMargins(16, 12, 16, 12)

        region_layout.addWidget(QLabel("Canal de destino:"))

        self.btn_br = QRadioButton("🇧🇷  Brasil (Português)")
        self.btn_us = QRadioButton("🇺🇸  EUA (English)")
        self.btn_br.setChecked(True)

        self.region_group = QButtonGroup(self)
        self.region_group.addButton(self.btn_br, 0)
        self.region_group.addButton(self.btn_us, 1)
        self.region_group.buttonClicked.connect(self._on_region_changed)

        region_layout.addWidget(self.btn_br)
        region_layout.addSpacing(20)
        region_layout.addWidget(self.btn_us)
        region_layout.addStretch()

        layout.addWidget(region_card)

        # ── Tabela de nichos ──────────────────────────────────────────────────
        self.table = QTableWidget(len(YouTubeSearcher.CATEGORIES), 4)
        self.table.setHorizontalHeaderLabels(["ID", "Nicho", "Potencial de Pagamento", "Facilidade de Viralizar"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white; 
                border-radius: 12px; 
                border: 1px solid #E5E5EA;
            }
            QHeaderView::section {
                background-color: #F5F5F7;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #1D1D1F;
                color: white;
            }
        """)
        self._populate_table()
        layout.addWidget(self.table)
        
        # ── Controles ─────────────────────────────────────────────────────────
        controls_card = QFrame()
        controls_card.setObjectName("resultCard")
        controls_layout = QHBoxLayout(controls_card)
        
        controls_layout.addWidget(QLabel("Quantidade de vídeos:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(5)
        controls_layout.addWidget(self.count_spin)
        
        controls_layout.addStretch()
        
        self.search_btn = QPushButton("BUSCAR E ADICIONAR À LISTA")
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.clicked.connect(self.start_search)
        controls_layout.addWidget(self.search_btn)
        
        layout.addWidget(controls_card)
        
        # ── Status ────────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #86868B; font-size: 12px;")
        layout.addWidget(self.status_label)

    def _populate_table(self):
        """Preenche a tabela de nichos."""
        self.table.setRowCount(0)
        for i, (key, val) in enumerate(YouTubeSearcher.CATEGORIES.items()):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(key))
            self.table.setItem(i, 1, QTableWidgetItem(val['name']))
            
            pay_item = QTableWidgetItem(val['pay'])
            if "Very high" in val['pay'] or "Muito alto" in val['pay']:
                pay_item.setForeground(QColor("#008000"))
            elif "High" in val['pay'] or "Alto" in val['pay']:
                pay_item.setForeground(QColor("#34C759"))
            self.table.setItem(i, 2, pay_item)
            
            viral_item = QTableWidgetItem(val['viral'])
            if "Extremely" in val['viral'] or "Extremamente" in val['viral']:
                viral_item.setForeground(QColor("#FF3B30"))
            elif "Very high" in val['viral'] or "Muito alto" in val['viral']:
                viral_item.setForeground(QColor("#007AFF"))
            self.table.setItem(i, 3, viral_item)

    def _on_region_changed(self, btn):
        """Chamado quando o usuário troca de região."""
        new_region = "US" if self.region_group.id(btn) == 1 else "BR"
        if new_region == self._current_region:
            return
        self.status_label.setText(f"Trocando para região {REGIONS[new_region]['label']}...")
        self._init_searcher(new_region)
        if self.searcher:
            self.status_label.setText(f"✓ Região alterada: {REGIONS[new_region]['label']}")
        else:
            self.status_label.setText("⚠ Erro ao trocar de região. Verifique a autenticação.")

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
        self.status_label.setText(f"Buscando '{cat_name}' em {region_label}...")
        
        self.worker = SearchWorker(self.searcher, category_key, count)
        self.worker.finished.connect(self.on_search_finished)
        self.worker.error.connect(self.on_search_error)
        self.worker.start()

    def on_search_finished(self, videos):
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if not videos:
            self.status_label.setText("Nenhum vídeo encontrado.")
            return

        # Mostra preview dos títulos encontrados
        preview = "\n".join(
            f"• [{v.get('channel','')}] {v['title'][:60]}{'…' if len(v['title'])>60 else ''}"
            for v in videos
        )
        confirm = QMessageBox.question(
            self,
            "Confirmar",
            f"Encontrados {len(videos)} vídeos:\n\n{preview}\n\nDeseja salvá-los em list.txt?",
            QMessageBox.Yes | QMessageBox.No,
        )
        
        if confirm == QMessageBox.Yes:
            added_count = save_to_list(videos)
            if added_count > 0:
                self.status_label.setText(f"✓ {added_count} novos vídeos adicionados ao list.txt.")
                QMessageBox.information(self, "Sucesso", f"{added_count} novos vídeos foram adicionados à sua lista.")
            else:
                self.status_label.setText("Nenhum vídeo novo (todos já estavam na lista).")
                QMessageBox.warning(self, "Aviso", "Todos os vídeos encontrados já estavam na sua lista.")
        else:
            self.status_label.setText("Operação cancelada.")

    def on_search_error(self, err_msg):
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Erro na busca.")
        QMessageBox.critical(self, "Erro", f"Ocorreu um erro durante a busca:\n{err_msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AutoListUI()
    window.show()
    sys.exit(app.exec())
