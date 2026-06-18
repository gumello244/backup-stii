import os

# ─── Modo de execução ─────────────────────────────────────────────────────────
# MODO_DEV = True  → usa pasta fictícia local para testes
# MODO_DEV = False → usa C:\ real (ambiente da prefeitura)
MODO_DEV = True

DISCO_RAIZ = (
    os.path.join(os.path.expanduser("~"), "Documents", "backup_dev")
    if MODO_DEV else r"C:\\"
)

# Pastas padrão do perfil Windows que o programa conhece
PASTAS_WINDOWS = {
    "Desktop":   "Desktop",
    "Documents": "Documents",
    "Downloads": "Downloads",
    "Pictures":  "Pictures",
    "Videos":    "Videos",
    "Music":     "Music",
    "Contacts":  "Contacts",
}
