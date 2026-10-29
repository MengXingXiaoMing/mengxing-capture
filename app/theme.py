"""统一的深色暖调主题（与用户既有项目风格一致：背景 rgb(34,30,27)）。"""
from __future__ import annotations

BG = "#221e1b"
BG_SOFT = "#2a2521"
BG_CARD = "#302a25"
BG_HOVER = "#3b332c"
BORDER = "#413931"
TEXT = "#efe6dc"
TEXT_DIM = "#a99c8e"
ACCENT = "#e8894a"
ACCENT_DOWN = "#c96f36"
DANGER = "#d9534f"
OK = "#5cb85c"

_TEMPLATE = f"""
* {{ outline: 0; }}
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#Title {{ font-size: 22px; font-weight: 600; }}
QLabel#Subtitle {{ color: {TEXT_DIM}; font-size: 12px; }}
QLabel#SectionTitle {{ font-size: 14px; font-weight: 600; color: {TEXT}; }}
QLabel#Hint {{ color: {TEXT_DIM}; font-size: 12px; }}
QLabel#Badge {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 2px 8px; color: {TEXT_DIM}; font-size: 11px;
}}
QFrame#Card {{
    background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 12px;
}}
QFrame#SideBar {{
    background: {BG_SOFT}; border-right: 1px solid {BORDER};
}}
QFrame#TopBar {{
    background: {BG_SOFT}; border-bottom: 1px solid {BORDER};
}}
QPushButton#Tab {{
    background: transparent; border: none; border-radius: 8px;
    padding: 0; color: {TEXT_DIM};
}}
QPushButton#Tab:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
QPushButton#Tab:checked {{
    background: {BG_CARD}; color: {ACCENT}; font-weight: 600;
}}
QPushButton {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 7px 14px; color: {TEXT};
}}
QPushButton:hover {{ background: {BG_HOVER}; border-color: #5a4d41; }}
QPushButton:pressed {{ background: #26211d; }}
QPushButton:disabled {{ color: #7a6f64; border-color: #352f29; }}
QPushButton#Primary {{
    background: {ACCENT}; border: 1px solid {ACCENT};
    color: #23180f; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #f09a5f; }}
QPushButton#Primary:pressed {{ background: {ACCENT_DOWN}; }}
QPushButton#Danger {{
    background: transparent; border: 1px solid #6d3a34; color: #e08a80;
}}
QPushButton#Danger:hover {{ background: #3a2622; }}
QPushButton#Nav {{
    background: transparent; border: none; border-radius: 8px;
    padding: 10px 14px; text-align: left; color: {TEXT_DIM};
}}
QPushButton#Nav:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
QPushButton#Nav:checked {{
    background: {BG_CARD}; color: {ACCENT}; font-weight: 600;
    border-left: 3px solid {ACCENT}; border-radius: 6px;
}}
QPushButton#Tool {{
    background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 4px 8px; font-size: 12px;
}}
QPushButton#Tool:hover {{ background: {BG_HOVER}; }}
QPushButton#Tool:checked {{ background: {ACCENT}; color: #23180f; }}
QPushButton#ToolIcon {{
    background: transparent; border: none; border-radius: 6px; padding: 0;
}}
QPushButton#ToolIcon:hover {{ background: {BG_HOVER}; }}
QPushButton#ToolIcon:disabled {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_SOFT}; border: 1px solid {BORDER};
    border-radius: 7px; padding: 6px 9px; selection-background-color: {ACCENT};
    selection-color: #23180f;
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox#Flat, QComboBox#Engine {{
    background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 4px 6px;
}}
QComboBox#Flat:hover, QComboBox#Engine:hover {{ background: {BG_HOVER}; }}
QComboBox#Flat:focus, QComboBox#Engine:focus {{ border-color: transparent; }}
QComboBox#Engine {{ color: {ACCENT}; }}
QTextEdit#Plain {{
    background: transparent; border: none; padding: 2px 0;
}}
QFrame#Divider {{ background: {BORDER}; border: none; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    selection-background-color: {BG_HOVER}; color: {TEXT}; padding: 4px;
}}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #4a4038; background: {BG_SOFT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
    image: url("__CHECK_ICON__");
}}
QCheckBox:disabled {{ color: #7a6f64; }}
QCheckBox::indicator:disabled {{ background: #2f2a25; border-color: #3a332c; }}
QCheckBox::indicator:checked:disabled {{
    background: #5c4a3c; border-color: #5c4a3c; image: none;
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
    background: {ACCENT};
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: {BG_SOFT}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{ background: {BG_HOVER}; color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: #4a4038; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #5d5147; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #4a4038; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM}; padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QMenu {{
    background: {BG_CARD}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px;
}}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {BG_HOVER}; color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QToolTip {{
    background: {BG_CARD}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 5px 8px; border-radius: 5px;
}}
QProgressBar {{
    background: {BG_SOFT}; border: none; border-radius: 4px;
    height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 10px;
    margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: {TEXT_DIM}; font-size: 12px;
}}
"""


def build_qss(check_icon: str = "") -> str:
    """生成样式表；check_icon 为复选框对勾图片的绝对路径（正斜杠）。"""
    return _TEMPLATE.replace("__CHECK_ICON__", check_icon)


QSS = build_qss()
