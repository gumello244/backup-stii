import os
import shutil
import hashlib
import datetime
import random

from core.conflitos import _arquivos_iguais


def _md5(caminho, bloco=65536):
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(bloco), b""):
            h.update(pedaco)
    return h.hexdigest()


def restaurar_arquivos(arquivos, decisoes, callback=None):
    """
    Fase 1 — copia e verifica cada arquivo (sem apagar o original).
    Fase 2 — só apaga os originais do backup se tudo correu bem.

    Rollback: se qualquer cópia falhar, todas as cópias já feitas são
    removidas e o backup original permanece 100% intacto.
    """
    restaurados  = 0
    ignorados    = 0
    erros        = 0
    total        = len(arquivos)

    copiados:    list[str] = []   # destinos copiados com sucesso
    para_apagar: list[str] = []   # origens a apagar só no final

    erro_fatal = None

    # ── Fase 1: copiar e verificar ────────────────────────────────────────────
    for idx, arq in enumerate(arquivos, 1):
        src  = arq["caminho_backup"]
        dest = arq["caminho_destino"]
        nome = arq["nome"]

        if callback:
            callback(idx, total, nome)

        try:
            # Arquivo idêntico no destino → ignora
            if os.path.exists(dest) and _arquivos_iguais(src, dest):
                ignorados += 1
                continue

            # Usuário escolheu manter o arquivo atual → ignora
            if src in decisoes and decisoes[src] == "manter":
                ignorados += 1
                continue

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)

            if _md5(src) != _md5(dest):
                raise IOError(f"Falha na verificação de integridade: {nome}")

            copiados.append(dest)
            para_apagar.append(src)
            restaurados += 1

        except Exception as e:
            print(f"[ERRO] {nome}: {e}")
            erros     += 1
            erro_fatal = str(e)
            break

    # ── Rollback ──────────────────────────────────────────────────────────────
    if erro_fatal:
        print(f"[ROLLBACK] Erro detectado. Desfazendo {len(copiados)} cópia(s)...")
        for dest_copiado in copiados:
            try:
                os.remove(dest_copiado)
                print(f"[ROLLBACK] Removido: {dest_copiado}")
            except Exception as e:
                print(f"[ROLLBACK] Não foi possível remover {dest_copiado}: {e}")

        return {
            "restaurados": 0,
            "ignorados":   ignorados,
            "erros":       erros,
            "chamado":     None,
            "rollback":    True,
            "erro_msg":    erro_fatal,
        }

    # ── Fase 2: apagar originais do backup ────────────────────────────────────
    for src_original in para_apagar:
        try:
            os.remove(src_original)
        except Exception as e:
            print(f"[AVISO] Não foi possível apagar original do backup: {src_original}: {e}")

    ano = datetime.datetime.now().year
    num = random.randint(1000, 9999)

    return {
        "restaurados": restaurados,
        "ignorados":   ignorados,
        "erros":       erros,
        "chamado":     f"{ano}-{num}",
        "rollback":    False,
        "erro_msg":    None,
    }
