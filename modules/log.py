from config import MODULOS_ATIVOS


def salvar_log(resultado, arquivos, matricula):
    """
    Salva um log detalhado da operação em .txt.
    Ainda não implementado — retorna None silenciosamente.
    """
    if not MODULOS_ATIVOS.get("log", False):
        return None

    # TODO: implementar geração do log em .txt
    pass
