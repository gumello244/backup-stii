import os
import re
import shutil
import hashlib
import datetime
import random

# ─── MODO DESENVOLVIMENTO ─────────────────────────────────────────────────────
# Quando True, o programa usa uma pasta local fictícia em vez do C:\ real.
# Mude para False quando for rodar no ambiente real da prefeitura.
MODO_DEV = True

DISCO_RAIZ = os.path.join(os.path.expanduser("~"), "Documents", "backup_dev") \
             if MODO_DEV else r"C:\\"

PASTAS_WINDOWS = {
    "Desktop":   "Desktop",
    "Documents": "Documents",
    "Downloads": "Downloads",
    "Pictures":  "Pictures",
    "Videos":    "Videos",
    "Music":     "Music",
    "Contacts":  "Contacts",
}


def detectar_usuario():
    matricula = os.environ.get("USERNAME", "").strip()
    if not matricula:
        raise RuntimeError("Não foi possível identificar o usuário logado.")

    try:
        import subprocess
        saida = subprocess.check_output(
            ["net", "user", matricula, "/domain"],
            stderr=subprocess.DEVNULL,
            encoding="cp850"
        )
        nome = ""
        for linha in saida.splitlines():
            if "Nome completo" in linha or "Full Name" in linha:
                partes = linha.split(None, 2)
                nome = partes[-1].strip() if len(partes) >= 3 else matricula
                break
        nome = nome or matricula
    except Exception:
        nome = matricula

    return matricula, nome


def _extrair_numero_chamado(nome_pasta):
    partes = nome_pasta.split("_")
    if len(partes) < 2:
        return None
    trecho = partes[1]
    match = re.search(r"(\d+)$", trecho)
    if match:
        return int(match.group(1))
    return None


def encontrar_pasta_backup():
    candidatas = []

    try:
        entradas = os.listdir(DISCO_RAIZ)
    except PermissionError:
        raise RuntimeError(f"Sem permissão para acessar {DISCO_RAIZ}.")

    for entrada in entradas:
        caminho = os.path.join(DISCO_RAIZ, entrada)
        if not os.path.isdir(caminho):
            continue
        numero = _extrair_numero_chamado(entrada)
        if numero is not None:
            candidatas.append((numero, caminho))

    if not candidatas:
        raise FileNotFoundError(
            f"Nenhuma pasta de backup encontrada em {DISCO_RAIZ}.\n"
            "Padrão esperado: PREFIXO_NUMERO_SUFIXO (ex: OS_27034_PMC_123122)"
        )

    candidatas.sort(key=lambda x: x[0], reverse=True)
    return candidatas[0][1]


def encontrar_pasta_usuario(matricula):
    pasta_backup = encontrar_pasta_backup()
    pasta_usuarios = os.path.join(pasta_backup, "USUARIOS")

    if not os.path.isdir(pasta_usuarios):
        raise FileNotFoundError(
            f"Pasta USUARIOS não encontrada dentro de:\n{pasta_backup}"
        )

    pasta_matricula = os.path.join(pasta_usuarios, matricula)

    if not os.path.isdir(pasta_matricula):
        raise FileNotFoundError(
            f"Nenhum backup encontrado para a matrícula {matricula}.\n"
            f"Caminho esperado: {pasta_matricula}"
        )

    return pasta_matricula


# ─── Arquivos ignorados automaticamente (lixo do Windows) ────────────────────
# Nomes exatos que sempre são pulados
NOMES_LIXO = {
    "thumbs.db",
    "desktop.ini",
    "ntuser.dat",
    "ntuser.dat.log",
    "ntuser.ini",
    ".ds_store",        # lixo do macOS que às vezes aparece em backups
}

# Extensões que sempre são puladas
EXTENSOES_LIXO = {
    ".tmp", ".temp",    # arquivos temporários
    ".lnk",             # atalhos do Windows
    ".url",             # atalhos de internet
    ".cache",           # cache genérico
    ".log",             # logs do sistema (não do usuário)
    ".bak",             # backups automáticos de programas
    ".part",            # downloads incompletos
}

# Pastas genéricas sempre ignoradas por completo
PASTAS_LIXO = {
    "__pycache__",
    ".git",
    "temp",
    "tmp",
}

# Subpastas do AppData que contêm dados reais do usuário e DEVEM ser restauradas.
# Tudo dentro de AppData que não bater com nenhum desses prefixos será ignorado.
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

    # Verifica nome exato
    if nome in NOMES_LIXO:
        return True

    # Verifica extensão
    ext = os.path.splitext(nome)[1].lower()
    if ext in EXTENSOES_LIXO:
        return True

    # Caminho relativo normalizado (sempre com /)
    relativo = os.path.relpath(caminho_backup, pasta_matricula).lower().replace("\\", "/")
    partes   = relativo.split("/")
    pastas   = partes[:-1]  # só as pastas, sem o nome do arquivo

    # Verifica pastas genéricas de lixo
    for parte in pastas:
        if parte in PASTAS_LIXO:
            return True

    # AppData: bloqueia tudo EXCETO as subpastas explicitamente permitidas
    if "appdata" in pastas:
        for permitida in APPDATA_PERMITIDAS:
            if relativo.startswith(permitida):
                return False   # subpasta permitida → não é lixo
        return True            # AppData mas fora das permitidas → lixo

    return False


def escanear_backup(matricula):
    pasta_matricula = encontrar_pasta_usuario(matricula)
    pasta_usuario_windows = os.path.expanduser("~")

    arquivos = []
    ignorados_lixo = 0

    for raiz, _, nomes in os.walk(pasta_matricula):
        for nome in nomes:
            caminho_backup = os.path.join(raiz, nome)

            if _e_lixo(caminho_backup, pasta_matricula):
                ignorados_lixo += 1
                continue

            relativo = os.path.relpath(caminho_backup, pasta_matricula)
            caminho_dest = os.path.join(pasta_usuario_windows, relativo)

            stat = os.stat(caminho_backup)
            pasta_rel = os.path.dirname(relativo)
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


def resumo_tipos(arquivos):
    contagem = {}
    for arq in arquivos:
        t = arq["tipo"]
        contagem[t] = contagem.get(t, 0) + 1
    return dict(sorted(contagem.items()))


def info_operacao(arquivos):
    total = len(arquivos)
    tamanho_b = sum(a["tamanho"] for a in arquivos)

    try:
        disco = shutil.disk_usage(os.path.expanduser("~"))
        espaco_str = f"{disco.free / (1024 ** 3):.1f} GB"
    except Exception:
        espaco_str = "—"

    min_est = max(1, int(tamanho_b / (100 * 1024 * 1024)))
    tamanho_str = (f"{tamanho_b / (1024**3):.1f} GB"
                   if tamanho_b >= 1024**3
                   else f"{tamanho_b / (1024**2):.0f} MB")

    return {
        "Total de arquivos": str(total),
        "Tamanho total":     tamanho_str,
        "Espaço disponível": espaco_str,
        "Tempo estimado":    f"~{min_est} min",
        "Data do backup":    (arquivos[0]["data_mod"].strftime("%d/%m/%Y")
                              if arquivos else "—"),
    }

def _fmt_tamanho(b):
    if b >= 1024 ** 3:
        return f"{b / (1024**3):.1f} GB"
    if b >= 1024 ** 2:
        return f"{b / (1024**2):.0f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b} B"


def gerar_preview(arquivos, conflitos):
    """Retorna dict com resumo completo para exibir antes da restauração."""
    total_b = sum(a["tamanho"] for a in arquivos)

    # Contagem e tamanho por tipo
    por_tipo = {}
    for arq in arquivos:
        t = arq["tipo"]
        if t not in por_tipo:
            por_tipo[t] = {"qtd": 0, "tamanho": 0}
        por_tipo[t]["qtd"]     += 1
        por_tipo[t]["tamanho"] += arq["tamanho"]

    # Espaço em disco
    try:
        disco        = shutil.disk_usage(os.path.expanduser("~"))
        espaco_livre = disco.free
        espaco_ok    = espaco_livre > total_b * 1.1
    except Exception:
        espaco_livre = None
        espaco_ok    = True

    # Arquivos idênticos no destino (serão ignorados)
    ignorados = sum(
        1 for arq in arquivos
        if os.path.exists(arq["caminho_destino"])
        and _arquivos_iguais(arq["caminho_backup"], arq["caminho_destino"])
    )

    min_est = max(1, int(total_b / (100 * 1024 * 1024)))

    return {
        "por_tipo":       por_tipo,
        "total_arquivos": len(arquivos),
        "total_tamanho":  total_b,
        "total_str":      _fmt_tamanho(total_b),
        "conflitos":      len(conflitos),
        "ignorados":      ignorados,
        "espaco_livre":   espaco_livre,
        "espaco_str":     _fmt_tamanho(espaco_livre) if espaco_livre is not None else "—",
        "espaco_ok":      espaco_ok,
        "tempo_min":      min_est,
        "data_backup":    (arquivos[0]["data_mod"].strftime("%d/%m/%Y") if arquivos else "—"),
    }


def _arquivos_iguais(caminho_a, caminho_b):
    try:
        sa = os.stat(caminho_a)
        sb = os.stat(caminho_b)
        if sa.st_size != sb.st_size:
            return False
        return abs(sa.st_mtime - sb.st_mtime) <= 2
    except Exception:
        return False


def detectar_conflitos(arquivos):
    conflitos = []
    for arq in arquivos:
        dest = arq["caminho_destino"]
        if os.path.exists(dest):
            if not _arquivos_iguais(arq["caminho_backup"], dest):
                conflitos.append(arq["caminho_backup"])
    return conflitos


def _md5(caminho, bloco=65536):
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(bloco), b""):
            h.update(pedaco)
    return h.hexdigest()


def restaurar_arquivos(arquivos, decisoes, callback=None):
    restaurados = 0
    ignorados   = 0
    erros       = 0
    total       = len(arquivos)

    for idx, arq in enumerate(arquivos, 1):
        src  = arq["caminho_backup"]
        dest = arq["caminho_destino"]
        nome = arq["nome"]

        if callback:
            callback(idx, total, nome)

        try:
            if os.path.exists(dest) and _arquivos_iguais(src, dest):
                ignorados += 1
                continue

            if src in decisoes and decisoes[src] == "manter":
                ignorados += 1
                continue

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)

            if _md5(src) != _md5(dest):
                raise IOError(f"Falha na verificação de integridade: {nome}")

            os.remove(src)
            restaurados += 1

        except Exception as e:
            print(f"[ERRO] {nome}: {e}")
            erros += 1

    ano = datetime.datetime.now().year
    num = random.randint(1000, 9999)

    return {
        "restaurados": restaurados,
        "ignorados":   ignorados,
        "erros":       erros,
        "chamado":     f"{ano}-{num}",
    }