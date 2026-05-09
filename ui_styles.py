# -*- coding: utf-8 -*-
# ui_styles.py - Design system and QSS for Viral Cutter UI

APPLE_MINIMAL_THEME = """
/* ── Apple Minimalist B&W Theme ─────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #FAFAFA;
    color: #1D1D1F;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
}

/* Sidebar / Navigation */
#sidebar {
    background-color: #F5F5F7;
    border-right: 1px solid #E5E5EA;
    min-width: 220px;
}

#sidebar QLabel {
    color: #1D1D1F;
}

#sidebar QPushButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    text-align: left;
    font-weight: 500;
    color: #86868B;
    margin: 4px 10px;
}

#sidebar QPushButton:hover {
    background-color: #E5E5EA;
    color: #1D1D1F;
}

#sidebar QPushButton[active="true"] {
    background-color: #1D1D1F;
    color: #FFFFFF;
    font-weight: 600;
}

/* Dashboard / Cards */
.Card, QFrame#resultCard, QGroupBox {
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E5E5EA;
    padding: 16px;
}

QFrame#resultCard:hover {
    border-color: #1D1D1F;
}

/* Buttons */
QPushButton#primaryButton {
    background-color: #1D1D1F;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 12px 24px;
    font-weight: 600;
    font-size: 14px;
}

QPushButton#primaryButton:hover {
    background-color: #424245;
}

QPushButton#primaryButton:pressed {
    background-color: #000000;
}

QPushButton#primaryButton:disabled {
    background-color: #E5E5EA;
    color: #86868B;
}

QPushButton#secondaryButton {
    background-color: #FFFFFF;
    color: #1D1D1F;
    border: 1px solid #D1D1D6;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton#secondaryButton:hover {
    background-color: #F5F5F7;
    border-color: #86868B;
}

QPushButton#secondaryButton:pressed {
    background-color: #E5E5EA;
}

/* Inputs */
QLineEdit, QSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 8px;
    padding: 10px 12px;
    color: #1D1D1F;
    font-size: 14px;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #1D1D1F;
}

QSpinBox::up-button, QSpinBox::down-button {
    background-color: #F5F5F7;
    border: none;
    width: 20px;
    border-radius: 4px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #E5E5EA;
}

/* ComboBox */
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 8px;
    padding: 10px 36px 10px 12px;
    color: #1D1D1F;
    font-size: 14px;
}

QComboBox:focus, QComboBox:on {
    border: 1px solid #1D1D1F;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #86868B;
    width: 0;
    height: 0;
}

QComboBox::down-arrow:on {
    border-top-color: #1D1D1F;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 8px;
    color: #1D1D1F;
    selection-background-color: #F5F5F7;
    selection-color: #1D1D1F;
    padding: 4px;
    outline: none;
}

/* CheckBox */
QCheckBox {
    spacing: 10px;
    color: #1D1D1F;
    font-size: 14px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid #D1D1D6;
    background-color: #FFFFFF;
}

QCheckBox::indicator:unchecked:hover {
    border: 1.5px solid #86868B;
}

QCheckBox::indicator:checked {
    background-color: #1D1D1F;
    border: 1.5px solid #1D1D1F;
    image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxOCAxOCI+PHBvbHlsaW5lIHBvaW50cz0iMyw5IDcsMTMgMTUsNSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyLjUiIGZpbGw9Im5vbmUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg==");
}

/* GroupBox */
QGroupBox {
    border: 1px solid #E5E5EA;
    border-radius: 12px;
    margin-top: 20px;
    padding-top: 18px;
    font-weight: 600;
    color: #1D1D1F;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 10px;
    left: 14px;
    color: #1D1D1F;
    background-color: #F5F5F7;
    border-radius: 6px;
    font-size: 12px;
}

/* Labels */
QLabel#headerLabel {
    font-size: 28px;
    font-weight: 700;
    color: #1D1D1F;
    margin-bottom: 10px;
    letter-spacing: -0.5px;
}

/* Progress Bar */
QProgressBar {
    background-color: #E5E5EA;
    border: none;
    border-radius: 8px;
    text-align: center;
    height: 12px;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #1D1D1F;
    border-radius: 8px;
}

/* Log View */
QPlainTextEdit#logView {
    background-color: #F5F5F7;
    border: 1px solid #E5E5EA;
    border-radius: 8px;
    font-family: 'SF Mono', 'Consolas', monospace;
    font-size: 12px;
    color: #86868B;
    padding: 12px;
}

/* ScrollBar */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #D1D1D6;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #86868B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
