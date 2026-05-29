# ── Paleta de cores ───────────────────────────────────────────────────────────
VERDE       = "#1D9E75"
VERDE_HOVER = "#178A63"
VERDE_LIGHT = "#E8F7F2"
CINZA       = "#B4B2A9"
CINZA_LIGHT = "#F0EEE7"
BRANCO      = "#FFFFFF"
FUNDO       = "#EDEAE2"
TEXTO_PRIM  = "#1E1E1C"
TEXTO_SEC   = "#6B6960"
TEXTO_TERT  = "#9C9A92"
BORDA       = "#DEDAD1"

ITEM_BG       = "#F7F6F1"
ITEM_CHECK_ON = "#C8EDE0"
ITEM_BORDA_ON = "#5BBF9F"

# ── Ícones por categoria de arquivo ──────────────────────────────────────────
ICONES_TIPO = {
    "PDF":        "📄",
    "Excel":      "📊",
    "Word":       "📝",
    "PowerPoint": "📑",
    "Imagens":    "🖼️",
    "Vídeos":     "🎬",
    "Áudio":      "🎵",
    "Compactado": "🗜️",
    "Texto":      "📃",
    "Outros":     "📁",
}

# ── Nomes em português por categoria ─────────────────────────────────────────
NOMES_PT = {
    "PDF":        "PDF",
    "Excel":      "Excel",
    "Word":       "Word",
    "PowerPoint": "PowerPoint",
    "Imagens":    "Imagens",
    "Vídeos":     "Vídeos",
    "Áudio":      "Áudio",
    "Compactado": "Compactados",
    "Texto":      "Texto",
    "Outros":     "Outros",
}

# ── Ícones por extensão de arquivo ───────────────────────────────────────────
ICONES_EXT = {
    ".xlsx": "📊", ".xls": "📊",
    ".docx": "📝", ".doc": "📝",
    ".pdf":  "📄",
    ".jpg":  "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️",
    ".mp4":  "🎬", ".avi":  "🎬", ".mov": "🎬",
    ".mp3":  "🎵", ".wav":  "🎵",
    ".pptx": "📑", ".ppt":  "📑",
    ".zip":  "🗜️", ".rar":  "🗜️",
    ".txt":  "📃",
}

# ── Ícones de pastas conhecidas do Windows ────────────────────────────────────
ICONES_PASTA = {
    "desktop":   "🖥️",
    "documents": "📁",
    "downloads": "⬇️",
    "pictures":  "🖼️",
    "videos":    "🎬",
    "music":     "🎵",
    "contacts":  "👤",
    "appdata":   "⚙️",
}

def icone_pasta(pasta_relativa: str) -> str:
    """Retorna o ícone adequado para uma pasta pelo seu caminho relativo."""
    if not pasta_relativa:
        return "🏠"
    primeira = pasta_relativa.replace("\\", "/").split("/")[0].lower()
    return ICONES_PASTA.get(primeira, "📂")

def nome_pasta_display(pasta_relativa: str) -> str:
    """Retorna o nome legível da pasta para exibição."""
    if not pasta_relativa:
        return "Pasta raiz"
    # Pega só a última parte do caminho para exibição amigável
    ultima = pasta_relativa.replace("\\", "/").split("/")[-1]
    return ultima if ultima else pasta_relativa