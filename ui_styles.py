# -*- coding: utf-8 -*-
# ui_styles.py - BLOOMBERG TERMINAL CORE ENGINE STYLE

# Bloomberg Terminal Palette
# Black:  #000000 (Background)
# Amber:  #FFB900 (Main text / Command text)
# Green:  #00FF00 (Success / Values / Positive)
# Blue:   #0000FF (Header / Command Bar)
# Red:    #FF0000 (Alerts / Errors)
# Gray:   #333333 (Borders)
# White:  #FFFFFF (Header text)
# Orange: #FF8000 (Warning / Processing)

BLOOMBERG_THEME = """
/* ── Bloomberg Terminal Core ────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #000000;
    color: #FFB900;
    font-family: "Consolas", "Monaco", "Cascadia Code", "Courier New", monospace;
    font-size: 13px;
    border: none;
}

/* Main Command Header (The Blue Bar) */
#commandHeader {
    background-color: #0000FF;
    color: #FFFFFF;
    font-weight: 900;
    border-bottom: 1px solid #FFFFFF;
    min-height: 25px;
}

#commandHeader QLabel {
    color: #FFFFFF;
    padding: 2px 10px;
    font-weight: bold;
    font-size: 12px;
    text-transform: uppercase;
}

/* Sidebar (Terminal Nav) */
#sidebar {
    background-color: #000000;
    border-right: 1px solid #333333;
}

#sidebar QLabel#navLabel {
    color: #000000;
    background-color: #FFB900;
    font-weight: 900;
    padding: 5px;
    font-size: 11px;
    text-transform: uppercase;
}

#sidebar QPushButton {
    background-color: #000000;
    color: #FFB900;
    border: none;
    border-bottom: 1px solid #1A1A1A;
    padding: 12px 10px;
    text-align: left;
    border-radius: 0px;
    margin: 0px;
}

#sidebar QPushButton:hover {
    background-color: #1A1A1A;
    color: #00FF00;
}

#sidebar QPushButton[active="true"] {
    background-color: #FFB900;
    color: #000000;
    font-weight: 900;
}

/* Containers & GroupBoxes */
QGroupBox {
    border: 1px solid #333333;
    margin-top: 15px;
    padding-top: 15px;
    font-weight: bold;
    color: #00FF00;
    text-transform: uppercase;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 7px;
    padding: 0 3px;
    background-color: #000000;
}

QFrame#card, QFrame#resultCard {
    background-color: #000000;
    border: 1px solid #333333;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #000000;
    border: 1px solid #333333;
    color: #00FF00;
    padding: 4px;
    selection-background-color: #00FF00;
    selection-color: #000000;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #FFB900;
}

/* Buttons */
QPushButton#primaryButton {
    background-color: #000000;
    color: #FFB900;
    border: 1px solid #FFB900;
    padding: 10px;
    font-weight: 900;
    text-transform: uppercase;
}

QPushButton#primaryButton:hover {
    background-color: #FFB900;
    color: #000000;
}

QPushButton#secondaryButton {
    background-color: #000000;
    color: #FFFFFF;
    border: 1px solid #333333;
    padding: 4px 8px;
}

QPushButton#secondaryButton:hover {
    background-color: #333333;
    color: #FFB900;
}

/* Checkboxes & RadioButtons */
QCheckBox, QRadioButton {
    color: #FFB900;
    spacing: 8px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #333333;
    background-color: #000000;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #00FF00;
    border: 1px solid #00FF00;
}

/* Tables */
QTableWidget {
    background-color: #000000;
    gridline-color: #1A1A1A;
    border: 1px solid #333333;
    color: #FFB900;
    selection-background-color: #1A1A1A;
}

QHeaderView::section {
    background-color: #0000FF;
    color: #FFFFFF;
    padding: 4px;
    border: 1px solid #FFFFFF;
    font-weight: bold;
    text-transform: uppercase;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #000000;
    width: 10px;
}

QScrollBar::handle:vertical {
    background: #333333;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #333333;
    background-color: #000000;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #00FF00;
}

/* Status Bar / Box */
#statusBox {
    margin: 10px 5px;
    padding: 8px;
    background-color: #000000;
    border: 1px solid #333333;
}

#statusHeader {
    font-size: 10px;
    font-weight: 900;
    color: #00FF00;
    text-transform: uppercase;
}

#engineStatus {
    font-size: 11px;
    color: #FFB900;
}

#contentStack {
    background-color: #000000;
    border-left: 1px solid #333333;
}

QLabel#headerLabel {
    color: #FFFFFF;
    background-color: #0000FF;
    padding: 4px 10px;
    font-weight: 900;
    text-transform: uppercase;
}
"""

THEMES = {
    "Bloomberg Terminal": BLOOMBERG_THEME
}
