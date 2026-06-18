import os
import datetime

from core.deteccao import encontrar_pasta_usuario


# ─── Classificação por tipo ───────────────────────────────────────────────────
EXTENSOES = {
    "PDF":        [".pdf"],
    "Excel":      [".xls", ".xlsx", ".xlsm", ".xlsb", ".csv"],
    "Word":       [".doc", ".docx", ".odt", ".rtf"],
    "PowerPoint": [".ppt", ".pptx", ".odp"],
    "Imagens":    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico"],
    "Vídeos":     [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"],
    "Áudio":      [".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma"],
    "Compactado": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Texto":      [".txt", ".log", ".md", ".xml", ".json", ".ini", ".cfg"],
}


def _classificar(nome_arquivo):
    ext = os.path.splitext(nome_arquivo)[1].lower()
    for tipo, exts in EXTENSOES.items():
        if ext in exts:
            return tipo
    return "Outros"


# ─── Filtro de lixo ───────────────────────────────────────────────────────────
NOMES_LIXO = {
    "thumbs.db",
    "desktop.ini",
    "ntuser.dat",
    "ntuser.dat.log",
    "ntuser.ini",
    ".ds_store",
}

EXTENSOES_LIXO = {
    ".tmp", ".temp",
    ".lnk",
    ".url",
    ".cache",
    ".log",
    ".bak",
    ".part",
}

PASTAS_LIXO = {
    "__pycache__",
    ".git",
    "temp",
    "tmp",
}

# Subpastas do AppData que contêm dados reais do usuário.
# Tudo dentro de AppData fora dessas será ignorado.
APPDATA_PERMITIDAS = [
    "appdata/local/microsoft/outlook",
    "appdata/roaming/microsoft/outlook",
    "appdata/roaming/microsoft/signatures",
    "appdata/roaming/microsoft/stationery",
    "appdata/roaming/microsoft/teams",
]


def _e_lixo(caminho_backup, pasta_matricula):
    """Retorna True se o arquivo deve ser ignorado por ser lixo do sistema."""
    nome = os.path.basename(caminho_backup).lower()

    if nome in NOMES_LIXO:
        return True

    ext = os.path.splitext(nome)[1].lower()
    if ext in EXTENSOES_LIXO:
        return True

    relativo = os.path.relpath(caminho_backup, pasta_matricula).lower().replace("\\", "/")
    partes   = relativo.split("/")
    pastas   = partes[:-1]

    for parte in pastas:
        if parte in PASTAS_LIXO:
            return True

    if "appdata" in pastas:
        for permitida in APPDATA_PERMITIDAS:
            if relativo.startswith(permitida):
                return False
        return True

    return False


# ─── Escaneamento ─────────────────────────────────────────────────────────────
def escanear_backup(matricula):
    """
    Varre a pasta do usuário no backup e retorna lista de dicts com
    informações de cada arquivo a ser restaurado.
    """
    pasta_matricula       = encontrar_pasta_usuario(matricula)
    pasta_usuario_windows = os.path.expanduser("~")

    arquivos       = []
    ignorados_lixo = 0

    for raiz, _, nomes in os.walk(pasta_matricula):
        for nome in nomes:
            caminho_backup = os.path.join(raiz, nome)

            if _e_lixo(caminho_backup, pasta_matricula):
                ignorados_lixo += 1
                continue

            relativo      = os.path.relpath(caminho_backup, pasta_matricula)
            caminho_dest  = os.path.join(pasta_usuario_windows, relativo)
            stat          = os.stat(caminho_backup)
            pasta_rel     = os.path.dirname(relativo)

            arquivos.append({
                "caminho_backup":  caminho_backup,
                "caminho_destino": caminho_dest,
                "nome":            nome,
                "pasta_relativa":  pasta_rel if pasta_rel != "." else "",
                "tipo":            _classificar(nome),
                "tamanho":         stat.st_size,
                "data_mod":        datetime.datetime.fromtimestamp(stat.st_mtime),
            })

    if ignorados_lixo:
        print(f"[INFO] {ignorados_lixo} arquivo(s) de lixo ignorado(s) automaticamente.")

    return arquivos
