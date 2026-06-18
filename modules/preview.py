import os
import shutil

from config import MODULOS_ATIVOS
from core.conflitos import _arquivos_iguais


def _fmt_tamanho(b):
    if b >= 1024 ** 3: return f"{b / (1024**3):.1f} GB"
    if b >= 1024 ** 2: return f"{b / (1024**2):.0f} MB"
    if b >= 1024:      return f"{b / 1024:.0f} KB"
    return f"{b} B"


def gerar_preview(arquivos, conflitos):
    """
    Retorna um dict com o resumo completo da operação para exibir
    antes de o usuário iniciar a restauração.

    Retorna None se o módulo estiver desativado em config.py.
    """
    if not MODULOS_ATIVOS.get("preview", False):
        return None

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

    # Arquivos idênticos no destino (serão ignorados na restauração)
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
