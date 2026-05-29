import os

usuario = os.environ.get("USERNAME", "usuario_teste")
base = os.path.join(os.path.expanduser("~"), "Documents", "backup_dev")
pasta_backup = os.path.join(base, "OS_27034_PMC_123122", "USUARIOS", usuario)

arquivos_fake = {
    "Desktop": [
        "relatorio_final.pdf",
        "foto_evento.jpg",
    ],
    "Documents": [
        "planilha_orcamento.xlsx",
        "contrato_servico.docx",
        "apresentacao_anual.pptx",
    ],
    "Downloads": [
        "manual_sistema.pdf",
        "comprovante.pdf",
    ],
    "Pictures": [
        "foto1.jpg",
        "foto2.png",
    ],
    "Videos": [
        "reuniao_gravada.mp4",
    ],
}

print(f"Criando ambiente dev em:\n{base}\n")

for pasta, arquivos in arquivos_fake.items():
    caminho_pasta = os.path.join(pasta_backup, pasta)
    os.makedirs(caminho_pasta, exist_ok=True)

    for nome_arquivo in arquivos:
        caminho_arquivo = os.path.join(caminho_pasta, nome_arquivo)
        with open(caminho_arquivo, "w") as f:
            f.write(f"arquivo fictício: {nome_arquivo}\n")
        print(f"  ✔ criado: {pasta}\\{nome_arquivo}")

print(f"\nPronto! Agora rode o main.py normalmente.")