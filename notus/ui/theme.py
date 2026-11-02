"""Colour tokens, palette and Qt style sheet."""
from __future__ import annotations

from string import Template

from PyQt6.QtGui import QColor, QPalette

ACCENTS = {
    "violet": "#7c5cff", "cyan": "#1fb6d4", "green": "#2fbf71", "orange": "#ff8a3d", "pink": "#ff5c9d",
}
THEMES = {
    "dark": dict(bg="#0d0f15", surface="#141720", surface2="#1b1f2b", border="#2a3040", text="#e7eaf3",
                 muted="#8b94aa", user_bubble="#252a3d", code_bg="#0a0c11", code_fg="#d7dcec", inline_bg="#232838"),
    "light": dict(bg="#f3f4f8", surface="#ffffff", surface2="#eceff6", border="#d9deea", text="#1b2030",
                  muted="#667089", user_bubble="#e4e8f6", code_bg="#eef0f7", code_fg="#1b2030", inline_bg="#e6e9f3"),
}


def colors(theme: str, accent: str) -> dict:
    c = dict(THEMES.get(theme, THEMES["dark"]))
    c["accent"] = ACCENTS.get(accent, ACCENTS["violet"])
    c["accent_hover"] = QColor(c["accent"]).lighter(115).name()
    c["accent_text"] = "#ffffff"
    c["danger"], c["ok"], c["warn"] = "#e5484d", "#2fbf71", "#f5a524"
    return c


QSS = Template("""
QWidget { color: $text; font-size: ${fs}pt; }
QMainWindow, QDialog, #Root, #Page, QStackedWidget, QScrollArea, #ScrollInner { background: $bg; }
QScrollArea { border: none; }
#Sidebar, #Topbar, #InputBar, #ParamsPanel { background: $surface; }
#Sidebar { border-right: 1px solid $border; }
#ParamsPanel { border-left: 1px solid $border; }
#Topbar { border-bottom: 1px solid $border; }
#InputBar { border-top: 1px solid $border; }
#Card { background: $surface; border: 1px solid $border; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#Muted { color: $muted; font-size: ${fs_small}pt; }
QLabel#Title { font-size: ${fs_big}pt; font-weight: 700; }
QLabel#H2 { font-size: ${fs_h2}pt; font-weight: 700; }
QLabel#Brand { font-size: ${fs_big}pt; font-weight: 800; }
QFrame#UserBubble { background: $user_bubble; border-radius: 14px; }
QFrame#BotBubble { background: $surface; border: 1px solid $border; border-radius: 14px; }
QPushButton { background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { border-color: $accent; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; border-color: $border; }
QPushButton#Primary { background: $accent; color: $accent_text; border: none; font-weight: 600; }
QPushButton#Primary:hover { background: $accent_hover; }
QPushButton#Primary:disabled { background: $border; color: $muted; }
QPushButton#Danger { color: $danger; }
QPushButton#Nav { text-align: left; padding: 9px 14px; border: none; background: transparent; }
QPushButton#Nav:hover { background: $surface2; }
QPushButton#Nav:checked { background: $surface2; color: $accent; font-weight: 600; }
QPushButton#Chip { padding: 4px 10px; border-radius: 12px; }
QPushButton:checked { border-color: $accent; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 5px 8px;
    selection-background-color: $accent; selection-color: $accent_text; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: $accent; }
QComboBox QAbstractItemView { background: $surface2; border: 1px solid $border; selection-background-color: $accent; outline: 0; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:hover { background: $surface2; }
QListWidget::item:selected { background: $surface2; color: $accent; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QSlider::groove:horizontal { height: 4px; background: $border; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: $accent; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: $border; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid $border; background: $surface2; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 4px; }
QStatusBar { background: $surface; border-top: 1px solid $border; }
QStatusBar QLabel { color: $muted; font-size: ${fs_small}pt; padding: 0 8px; }
QMenu { background: $surface2; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: $accent; color: $accent_text; }
""")


def apply(app, theme: str, accent: str, font_size: int) -> dict:
    c = colors(theme, accent)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface2"), (QPalette.ColorRole.AlternateBase, "surface"),
        (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "surface2"),
        (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "accent_text"), (QPalette.ColorRole.ToolTipBase, "surface2"),
        (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Link, "accent"),
    ):
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
    fs = max(8, min(16, int(font_size)))
    app.setStyleSheet(QSS.substitute(c, fs=fs, fs_small=max(7, fs - 1), fs_h2=fs + 2, fs_big=fs + 6))
    return c
