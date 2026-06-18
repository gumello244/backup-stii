import os


def _arquivos_iguais(caminho_a, caminho_b):
    """
    Compara dois arquivos por tamanho e data de modificação.
    Retorna True se forem considerados idênticos (sem necessidade de restaurar).
    """
    try:
        sa = os.stat(caminho_a)
        sb = os.stat(caminho_b)
        if sa.st_size != sb.st_size:
            return False
        return abs(sa.st_mtime - sb.st_mtime) <= 2
    except Exception:
        return False


def detectar_conflitos(arquivos):
    """
    Retorna lista de caminhos de backup cujo destino já existe
    e é diferente do arquivo de origem (conflito real).
    """
    conflitos = []
    for arq in arquivos:
        dest = arq["caminho_destino"]
        if os.path.exists(dest):
            if not _arquivos_iguais(arq["caminho_backup"], dest):
                conflitos.append(arq["caminho_backup"])
    return conflitos
