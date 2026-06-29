"""Remos design tokens and Qt stylesheet.

Light-only theme with dark pastel blue accent.  Segoe UI (native Windows).
All color constants are prefixed RM_ for grep-ability.

Example:
    from ui.assets import STYLESHEET, RM_ACCENT
    app.setStyleSheet(STYLESHEET)
"""
import os
import sys

# ------------------------------------------------------------------
# Color Tokens
# ------------------------------------------------------------------

# Azul pastel escuro — acento principal
RM_ACCENT = "#3B6EA5"
RM_ACCENT_HOVER = "#2C5282"
RM_ACCENT_PRESSED = "#1E3A5F"

# Vermelho pastel escuro — erro, cancelar, perigo
RM_RED = "#C0392B"
RM_RED_SOFT = "#FADBD8"

# Amarelo pastel escuro — aviso, arquivos pulados
RM_YELLOW = "#B7950B"
RM_YELLOW_SOFT = "#FCF3CF"

# Verde — sucesso
RM_GREEN = "#27AE60"
RM_GREEN_SOFT = "#D5F5E3"

# Bento Hero — azul suave
RM_HERO_BG    = "#EBF3FC"
RM_HERO_BORDER = "#D5E5F7"
# Bento Success — verde suave
RM_SUCCESS_BG    = "#EAF7ED"
RM_SUCCESS_BORDER = "#D1F2D9"
# Bento Danger — vermelho suave
RM_DANGER_BG    = "#FDF2F2"
RM_DANGER_BORDER = "#FBD5D5"

# Superfícies
RM_BG = "#FFFFFF"
RM_SURFACE = "#F9F9F9"
RM_BORDER = "#EEEEEE"

# Texto
RM_TEXT = "#1A202C"
RM_TEXT_MUTED = "#718096"

# ------------------------------------------------------------------
# Asset path helper
# ------------------------------------------------------------------


def asset_path(filename: str) -> str:
    """Resolve the absolute path to a file inside ui/assets/.

    Handles both development and frozen (PyInstaller) environments.

    Example:
        icon = asset_path("icon.ico")
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", filename)


# ------------------------------------------------------------------
# Stylesheet
# ------------------------------------------------------------------

STYLESHEET = f"""
/* ---- Global ---- */
QMainWindow {{
    background-color: {RM_BG};
}}
QWidget {{
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 14px;
    color: {RM_TEXT};
    background-color: {RM_BG};
}}

/* ---- Cards / Surfaces ---- */
QFrame#SurfaceCard {{
    background-color: {RM_SURFACE};
    border: 1px solid {RM_BORDER};
    border-radius: 10px;
}}

/* ---- Labels ---- */
QLabel#ViewTitle {{
    font-size: 22px;
    font-weight: bold;
    color: {RM_TEXT};
    background: transparent;
}}
QLabel#ViewSubtitle {{
    font-size: 14px;
    color: {RM_TEXT_MUTED};
    background: transparent;
}}
QLabel#AccentLabel {{
    font-size: 14px;
    color: {RM_ACCENT};
    font-weight: 600;
    background: transparent;
}}
QLabel#MutedLabel {{
    font-size: 12px;
    color: {RM_TEXT_MUTED};
    background: transparent;
}}
QLabel#ErrorLabel {{
    font-size: 14px;
    color: {RM_RED};
    background: transparent;
}}
QLabel#SuccessLabel {{
    font-size: 14px;
    color: {RM_GREEN};
    background: transparent;
}}
QLabel#WarningLabel {{
    font-size: 14px;
    color: {RM_YELLOW};
    background: transparent;
}}

/* ---- Buttons ---- */
QPushButton#PrimaryButton {{
    background-color: {RM_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 24px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {RM_ACCENT_HOVER};
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {RM_ACCENT_PRESSED};
}}
QPushButton#PrimaryButton:disabled {{
    background-color: {RM_BORDER};
    color: {RM_TEXT_MUTED};
}}

QPushButton#SecondaryButton {{
    background-color: {RM_SURFACE};
    color: {RM_TEXT};
    border: 1px solid {RM_BORDER};
    border-radius: 8px;
    padding: 8px 24px;
    font-size: 14px;
}}
QPushButton#SecondaryButton:hover {{
    background-color: #EDF2F7;
}}
QPushButton#SecondaryButton:pressed {{
    background-color: #E2E8F0;
}}

QPushButton#DangerButton {{
    background-color: {RM_RED};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 24px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#DangerButton:hover {{
    background-color: #A93226;
}}

QPushButton#LinkButton {{
    background: transparent;
    color: {RM_ACCENT};
    border: none;
    font-size: 13px;
    text-decoration: underline;
    padding: 4px;
}}
QPushButton#LinkButton:hover {{
    color: {RM_ACCENT_HOVER};
}}

/* ---- Progress Bar ---- */
QProgressBar {{
    border: 1px solid {RM_BORDER};
    border-radius: 6px;
    background-color: #EDF2F7;
    text-align: center;
    font-size: 12px;
    color: {RM_TEXT};
    min-height: 20px;
}}
QProgressBar::chunk {{
    background-color: {RM_ACCENT};
    border-radius: 5px;
}}

/* ---- Scroll Area ---- */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    border: none;
    background: #EDF2F7;
    width: 8px;
    margin: 4px 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #CBD5E0;
    min-height: 20px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
}}

/* ---- Checkboxes ---- */
QCheckBox {{
    spacing: 8px;
    font-size: 14px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {RM_BORDER};
    border-radius: 4px;
    background-color: {RM_SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {RM_ACCENT};
    border-color: {RM_ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {RM_ACCENT};
}}

/* Checkboxes styled like SONICO 2.0 */
QCheckBox#DefaultCheckbox {{
    background-color: #F9F9F9;
    border: 2px solid #DDDDDD;
    border-radius: 6px;
    padding: 6px 10px;
    spacing: 8px;
    font-size: 13px;
    color: {RM_TEXT};
}}
QCheckBox#DefaultCheckbox:hover {{
    border-color: #bbbbbb;
}}
QCheckBox#DefaultCheckbox::indicator {{
    width: 10px;
    height: 10px;
    border: none;
    border-radius: 2px;
    background-color: transparent;
}}
QCheckBox#DefaultCheckbox::indicator:checked {{
    background-color: {RM_ACCENT};
}}
QCheckBox#DefaultCheckbox::indicator:hover {{
    border-color: #bbbbbb;
}}

/* Custom Folder Option Row */
QFrame#FolderOptionRow {{
    background-color: #F9F9F9;
    border: 2px solid #DDDDDD;
    border-radius: 6px;
}}
QFrame#FolderOptionRow:hover {{
    border-color: #bbbbbb;
}}
QCheckBox#FolderOptionCheckbox {{
    background: transparent;
    border: none;
    padding: 0px;
    margin: 0px;
}}
QCheckBox#FolderOptionCheckbox::indicator {{
    width: 10px;
    height: 10px;
    border: none;
    border-radius: 2px;
    background-color: transparent;
}}
QCheckBox#FolderOptionCheckbox::indicator:checked {{
    background-color: {RM_ACCENT};
}}
QCheckBox#FolderOptionCheckbox::indicator:hover {{
    border-color: #bbbbbb;
}}
QLabel#FolderTitleLabel {{
    font-size: 13px;
    font-weight: 600;
    color: {RM_TEXT};
    background: transparent;
}}
QLabel#FolderCountLabel {{
    font-size: 11px;
    color: {RM_TEXT_MUTED};
    background: transparent;
}}
QLabel#FolderSizeLabel {{
    font-size: 12px;
    font-weight: bold;
    color: {RM_ACCENT};
    background: transparent;
}}

/* ---- Bento Grid Design System ---- */
QFrame#BentoCard {{
    background-color: {RM_SURFACE};
    border: 1px solid {RM_BORDER};
    border-radius: 12px;
}}
QFrame#BentoCardHero {{
    background-color: {RM_HERO_BG};
    border: 1px solid {RM_HERO_BORDER};
    border-radius: 12px;
}}
QFrame#BentoCardSuccess {{
    background-color: {RM_SUCCESS_BG};
    border: 1px solid {RM_SUCCESS_BORDER};
    border-radius: 12px;
}}
QFrame#BentoCardDanger {{
    background-color: {RM_DANGER_BG};
    border: 1px solid {RM_DANGER_BORDER};
    border-radius: 12px;
}}
QLabel#BentoTitle {{
    font-size: 9px;
    font-weight: 800;
    color: {RM_TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#BentoValue {{
    font-size: 20px;
    font-weight: 700;
    color: {RM_TEXT};
    background: transparent;
}}
QLabel#BentoValueHero {{
    font-size: 32px;
    font-weight: 800;
    color: {RM_ACCENT};
    letter-spacing: -1px;
    background: transparent;
}}
QLabel#BentoValueSuccess {{
    font-size: 20px;
    font-weight: 800;
    color: {RM_GREEN};
    background: transparent;
}}
QLabel#BentoValueDanger {{
    font-size: 20px;
    font-weight: 800;
    color: {RM_RED};
    background: transparent;
}}
QLabel#BentoSub {{
    font-size: 11px;
    color: {RM_TEXT_MUTED};
    background: transparent;
}}
"""
