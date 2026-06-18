import os
import re

from core.config import DISCO_RAIZ


def detectar_usuario():
    """Retorna (matricula, nome_completo) do usuário logado no Windows."""
    matricula = os.environ.get("USERNAME", "").strip()
    if not matricula:
        raise RuntimeError("Não foi possível identificar o usuário logado.")

    try:
        import subprocess
        saida = subprocess.check_output(
            ["net", "user", matricula, "/domain"],
            stderr=subprocess.DEVNULL,
            encoding="cp850",
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
    """Extrai o número do chamado do nome da pasta de backup."""
    partes = nome_pasta.split("_")
    if len(partes) < 2:
        return None
    trecho = partes[1]
    match = re.search(r"(\d+)$", trecho)
    return int(match.group(1)) if match else None


def encontrar_pasta_backup():
    """
    Varre DISCO_RAIZ e retorna o caminho da pasta de backup mais recente.
    Padrão esperado: PREFIXO_NUMERO_SUFIXO (ex: OS_27034_PMC_123122)
    """
    try:
        entradas = os.listdir(DISCO_RAIZ)
    except PermissionError:
        raise RuntimeError(f"Sem permissão para acessar {DISCO_RAIZ}.")

    candidatas = []
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
    """Retorna o caminho da pasta do usuário dentro do backup."""
    pasta_backup   = encontrar_pasta_backup()
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
