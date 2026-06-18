import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QProgressBar, QScrollArea,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont, QPixmap, QColor

from core.deteccao   import detectar_usuario
from core.escaneamento import escanear_backup
from core.conflitos  import detectar_conflitos
from core.restauracao import restaurar_arquivos
from modules.preview import gerar_preview
from modules.log     import salvar_log
from ui.estilos import (
    VERDE, VERDE_HOVER, VERDE_LIGHT, CINZA, CINZA_LIGHT,
    BRANCO, FUNDO, TEXTO_PRIM, TEXTO_SEC, TEXTO_TERT, BORDA,
    ITEM_BORDA_ON,
)
from ui.widgets import LinhaPasta, LinhaArquivo, _sombra


# ── Workers ───────────────────────────────────────────────────────────────────
class WorkerDetectar(QThread):
    def __init__(self, sinais):
        super().__init__()
        self.sinais = sinais

    def run(self):
        try:
            matricula, nome = detectar_usuario()
            self.sinais.usuario_detectado.emit(matricula, nome)
            arquivos = escanear_backup(matricula)
            self.sinais.backup_encontrado.emit(arquivos)
            conflitos = detectar_conflitos(arquivos)
            self.sinais.conflitos_encontrados.emit(conflitos)
        except Exception as e:
            self.sinais.erro.emit(str(e))


class WorkerRestaurar(QThread):
    def __init__(self, arquivos, decisoes, sinais):
        super().__init__()
        self.arquivos = arquivos
        self.decisoes = decisoes
        self.sinais   = sinais

    def run(self):
        def progresso(atual, total, nome_arquivo):
            pct = int((atual / total) * 100) if total else 0
            self.sinais.progresso.emit(pct, nome_arquivo)
        resultado = restaurar_arquivos(self.arquivos, self.decisoes, callback=progresso)
        self.sinais.finalizado.emit(resultado)


# ── Sinais ────────────────────────────────────────────────────────────────────
class Sinais(QObject):
    usuario_detectado     = pyqtSignal(str, str)
    backup_encontrado     = pyqtSignal(list)
    conflitos_encontrados = pyqtSignal(list)
    erro                  = pyqtSignal(str)
    progresso             = pyqtSignal(int, str)
    finalizado            = pyqtSignal(dict)


# ── Janela principal ──────────────────────────────────────────────────────────
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Restauração de Backup — Prefeitura")
        self.setFixedSize(740, 680)
        self.setStyleSheet(f"background: {FUNDO};")

        self.matricula = ""
        self.arquivos  = []
        self.conflitos = []
        self.decisoes  = {}
        self._linhas_arquivo: list[LinhaArquivo] = []

        self.sinais = Sinais()
        self.sinais.usuario_detectado.connect(self._on_usuario)
        self.sinais.backup_encontrado.connect(self._preencher_info)
        self.sinais.conflitos_encontrados.connect(self._mostrar_conflitos)
        self.sinais.erro.connect(self._on_erro)
        self.sinais.progresso.connect(self._atualizar_progresso)
        self.sinais.finalizado.connect(self._finalizar)

        central = QWidget()
        central.setStyleSheet(f"background: {FUNDO};")
        self.setCentralWidget(central)

        self.layout_principal = QVBoxLayout(central)
        self.layout_principal.setContentsMargins(20, 20, 20, 20)
        self.layout_principal.setSpacing(12)

        self._build_header()
        self._build_info()
        self._build_restore_card()
        self.layout_principal.addStretch()

        self.worker_detectar = WorkerDetectar(self.sinais)
        self.worker_detectar.start()

    def _card(self, parent_layout=None):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BRANCO};
                border-radius: 14px;
                border: 1px solid {BORDA};
            }}
        """)
        card.setGraphicsEffect(_sombra())
        if parent_layout:
            parent_layout.addWidget(card)
        return card

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        self._card_header = QFrame(self.centralWidget())
        self._card_header.setStyleSheet(f"""
            QFrame {{
                background: {BRANCO};
                border-radius: 14px;
                border: 1px solid {BORDA};
            }}
        """)
        self._card_header.setGraphicsEffect(_sombra())
        self.layout_principal.addWidget(self._card_header)

        layout = QHBoxLayout(self._card_header)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        self._emoji_lbl = QLabel(self._card_header)
        self._emoji_lbl.setFixedSize(44, 44)
        pix = QPixmap("ligne.png")
        if not pix.isNull():
            self._emoji_lbl.setPixmap(pix.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self._emoji_lbl.setText("🏛️")
            self._emoji_lbl.setStyleSheet("font-size: 28px; background: transparent; border: none;")
        self._emoji_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._emoji_lbl)

        self._info_widget = QWidget(self._card_header)
        self._info_widget.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(self._info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(3)

        self._titulo_lbl = QLabel("Restauração de Backup", self._info_widget)
        self._titulo_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {TEXTO_PRIM}; background: transparent; border: none;"
        )
        info_layout.addWidget(self._titulo_lbl)

        self.lbl_matricula = QLabel("Identificando usuário...", self._info_widget)
        self.lbl_matricula.setStyleSheet(
            f"font-size: 12px; color: {TEXTO_SEC}; background: transparent; border: none;"
        )
        info_layout.addWidget(self.lbl_matricula)

        layout.addWidget(self._info_widget, stretch=1)

        self.badge = QLabel("", self._card_header)
        self.badge.setStyleSheet(f"""
            color: {VERDE}; font-size: 12px; font-weight: bold;
            background: {VERDE_LIGHT}; border-radius: 10px; border: none; padding: 4px 10px;
        """)
        self.badge.setVisible(False)
        layout.addWidget(self.badge)

    # ── Cards duplos: Arquivos + Operação ─────────────────────────────────────
    def _build_info(self):
        self._row_info = QWidget()
        self._row_info.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(self._row_info)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        self.layout_principal.addWidget(self._row_info)

        # ── Card arquivos ─────────────────────────────────────────────────────
        self._card_arq = self._card()
        arq_layout = QVBoxLayout(self._card_arq)
        arq_layout.setContentsMargins(16, 14, 16, 10)
        arq_layout.setSpacing(6)

        hdr_widget = QWidget()
        hdr_widget.setStyleSheet("background: transparent; border: none;")
        hdr_layout = QHBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(6)

        titulo_arq = QLabel("ARQUIVOS NO BACKUP")
        titulo_arq.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {TEXTO_TERT}; letter-spacing: 1px; border: none;"
        )
        hdr_layout.addWidget(titulo_arq, stretch=1)

        self.btn_sel_todos = QPushButton("Selecionar todos")
        self.btn_sel_todos.setFixedHeight(22)
        self.btn_sel_todos.setCursor(Qt.PointingHandCursor)
        self.btn_sel_todos.setVisible(False)
        self.btn_sel_todos.setStyleSheet(f"""
            QPushButton {{
                background: {VERDE_LIGHT}; color: {VERDE};
                border-radius: 6px; border: 1px solid {ITEM_BORDA_ON};
                font-size: 11px; font-weight: bold; padding: 0px 8px;
            }}
            QPushButton:hover {{ background: #D0F0E4; }}
        """)
        self.btn_sel_todos.clicked.connect(self._selecionar_todos)
        hdr_layout.addWidget(self.btn_sel_todos)

        self.btn_desm_todos = QPushButton("Desmarcar todos")
        self.btn_desm_todos.setFixedHeight(22)
        self.btn_desm_todos.setCursor(Qt.PointingHandCursor)
        self.btn_desm_todos.setVisible(False)
        self.btn_desm_todos.setStyleSheet(f"""
            QPushButton {{
                background: {CINZA_LIGHT}; color: {TEXTO_SEC};
                border-radius: 6px; border: 1px solid {BORDA};
                font-size: 11px; font-weight: bold; padding: 0px 8px;
            }}
            QPushButton:hover {{ background: #E2DFD8; }}
        """)
        self.btn_desm_todos.clicked.connect(self._desmarcar_todos)
        hdr_layout.addWidget(self.btn_desm_todos)

        arq_layout.addWidget(hdr_widget)

        sep = QFrame(self._card_arq)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {BORDA}; border: none; background: {BORDA}; max-height: 1px;")
        arq_layout.addWidget(sep)

        scroll = QScrollArea(self._card_arq)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(185)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
            QScrollBar::handle:vertical { background: #CCCABF; border-radius: 3px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 4, 0)
        self.scroll_layout.setSpacing(2)

        scroll.setWidget(self.scroll_content)
        arq_layout.addWidget(scroll)

        self._lbl_contagem = QLabel("")
        self._lbl_contagem.setStyleSheet(
            f"font-size: 11px; color: {TEXTO_TERT}; border: none; background: transparent;"
        )
        self._lbl_contagem.setAlignment(Qt.AlignRight)
        self._lbl_contagem.setVisible(False)
        arq_layout.addWidget(self._lbl_contagem)

        row_layout.addWidget(self._card_arq, stretch=1)

        # ── Card operação ─────────────────────────────────────────────────────
        self._card_op = self._card()
        op_layout = QVBoxLayout(self._card_op)
        op_layout.setContentsMargins(14, 12, 14, 12)
        op_layout.setSpacing(0)

        titulo_op = QLabel("INFORMAÇÕES DA OPERAÇÃO", self._card_op)
        titulo_op.setStyleSheet(
            f"font-size: 9px; font-weight: bold; color: {TEXTO_TERT}; "
            f"letter-spacing: 1.2px; border: none; padding-bottom: 8px;"
        )
        op_layout.addWidget(titulo_op)

        self.op_frame_layout = QVBoxLayout()
        self.op_frame_layout.setSpacing(0)
        self.op_frame_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.addLayout(self.op_frame_layout)
        op_layout.addStretch()

        row_layout.addWidget(self._card_op, stretch=1)

    def _linha_op(self, label, valor, ultimo=False, negrito=False, cor_valor=None):
        """Cria uma linha no card de operação e retorna o QLabel do valor."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXTO_SEC}; background: transparent; border: none;"
        )
        layout.addWidget(lbl)

        cor  = cor_valor or TEXTO_PRIM
        peso = "bold" if negrito else "500"
        val  = QLabel(valor)
        val.setStyleSheet(
            f"font-size: 11px; font-weight: {peso}; color: {cor}; "
            f"background: transparent; border: none;"
        )
        val.setAlignment(Qt.AlignRight)
        layout.addWidget(val, stretch=1)

        self.op_frame_layout.addWidget(row)

        if not ultimo:
            div = QFrame()
            div.setFrameShape(QFrame.HLine)
            div.setFixedHeight(1)
            div.setStyleSheet(f"background: {BORDA}; border: none; margin: 0px 4px;")
            self.op_frame_layout.addWidget(div)

        return val

    def _preencher_preview(self, preview):
        """Monta o card 'INFORMAÇÕES DA OPERAÇÃO'. Se preview for None, exibe mensagem simples."""
        if preview is None:
            self._linha_op("Preview", "desativado", ultimo=True)
            return

        from ui.estilos import NOMES_PT

        self._tipos_op     = sorted(preview["por_tipo"].keys())
        self._lbl_op_tipo  = {}

        for tipo in self._tipos_op:
            nome_pt = NOMES_PT.get(tipo, tipo)
            lbl     = self._linha_op(nome_pt, "")
            self._lbl_op_tipo[tipo] = lbl

        # Separador entre tipos e totais
        sep_wrapper = QWidget()
        sep_wrapper.setStyleSheet("background: transparent;")
        sep_wrapper.setFixedHeight(10)
        sep_h = QHBoxLayout(sep_wrapper)
        sep_h.setContentsMargins(4, 4, 4, 4)
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.HLine)
        sep_line.setFixedHeight(1)
        sep_line.setStyleSheet(f"background: {BORDA}; border: none;")
        sep_h.addWidget(sep_line)
        self.op_frame_layout.addWidget(sep_wrapper)

        self._lbl_op_total  = self._linha_op("Total",          "", negrito=True)
        self._lbl_op_espaco = self._linha_op("Espaço livre",   "")
        self._lbl_op_tempo  = self._linha_op("Tempo estimado", "", ultimo=True)

        self._atualizar_preview(preview)

    def _atualizar_preview(self, preview=None):
        """Recalcula e atualiza os valores do painel com os arquivos selecionados."""
        if not hasattr(self, "_lbl_op_total"):
            return

        from ui.estilos import NOMES_PT

        if preview is None:
            preview = gerar_preview(self._arquivos_selecionados(), self.conflitos)

        if preview is None:
            return

        for tipo, lbl in self._lbl_op_tipo.items():
            dados = preview["por_tipo"].get(tipo)
            if dados and dados["qtd"] > 0:
                lbl.setText(f"{dados['qtd']} arq.  ·  {self._fmt(dados['tamanho'])}")
                lbl.setStyleSheet(
                    f"font-size: 11px; font-weight: 500; color: {TEXTO_PRIM}; "
                    f"background: transparent; border: none;"
                )
            else:
                lbl.setText("—")
                lbl.setStyleSheet(
                    f"font-size: 11px; font-weight: 400; color: {TEXTO_TERT}; "
                    f"background: transparent; border: none;"
                )

        total_qtd = preview["total_arquivos"]
        plural    = "s" if total_qtd != 1 else ""
        self._lbl_op_total.setText(f"{total_qtd} arquivo{plural}  ·  {preview['total_str']}")

        if not preview["espaco_ok"]:
            self._lbl_op_espaco.setText(f"{preview['espaco_str']}  ⚠")
            self._lbl_op_espaco.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #C0392B; background: transparent; border: none;"
            )
        else:
            self._lbl_op_espaco.setText(f"{preview['espaco_str']}  ✓")
            self._lbl_op_espaco.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #1D9E75; background: transparent; border: none;"
            )

        self._lbl_op_tempo.setText(f"~{preview['tempo_min']} min")

    @staticmethod
    def _fmt(b):
        if b >= 1024 ** 3: return f"{b / (1024**3):.1f} GB"
        if b >= 1024 ** 2: return f"{b / (1024**2):.0f} MB"
        if b >= 1024:      return f"{b / 1024:.0f} KB"
        return f"{b} B"

    # ── Card restauração ──────────────────────────────────────────────────────
    def _build_restore_card(self):
        self.card_restore = self._card(self.layout_principal)

        self.restore_layout = QVBoxLayout(self.card_restore)
        self.restore_layout.setContentsMargins(20, 16, 20, 16)
        self.restore_layout.setSpacing(10)

        self.conflitos_widget = QWidget(self.card_restore)
        self.conflitos_widget.setStyleSheet("background: transparent; border: none;")
        self.conflitos_layout = QVBoxLayout(self.conflitos_widget)
        self.conflitos_layout.setContentsMargins(0, 0, 0, 0)
        self.conflitos_layout.setSpacing(6)
        self.conflitos_widget.setVisible(False)
        self.restore_layout.addWidget(self.conflitos_widget)

        titulo = QLabel("RESTAURAÇÃO", self.card_restore)
        titulo.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {TEXTO_TERT}; letter-spacing: 1px; border: none;"
        )
        self.restore_layout.addWidget(titulo)

        self.barra = QProgressBar(self.card_restore)
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        self.barra.setStyleSheet(f"""
            QProgressBar {{ background: {CINZA_LIGHT}; border-radius: 4px; border: none; }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {VERDE}, stop:1 #25C992);
                border-radius: 4px;
            }}
        """)
        self.restore_layout.addWidget(self.barra)

        self._meta_widget = QWidget(self.card_restore)
        self._meta_widget.setStyleSheet("background: transparent; border: none;")
        meta_layout = QHBoxLayout(self._meta_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_prog = QLabel("Aguardando início", self._meta_widget)
        self.lbl_prog.setStyleSheet(f"font-size: 12px; color: {TEXTO_SEC}; border: none;")
        meta_layout.addWidget(self.lbl_prog, stretch=1)

        self.lbl_pct = QLabel("0%", self._meta_widget)
        self.lbl_pct.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {VERDE}; border: none;"
        )
        self.lbl_pct.setAlignment(Qt.AlignRight)
        meta_layout.addWidget(self.lbl_pct)

        self.restore_layout.addWidget(self._meta_widget)

        self.btn_iniciar = QPushButton("Iniciar restauração")
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setFixedHeight(42)
        self.btn_iniciar.setCursor(Qt.PointingHandCursor)
        self.btn_iniciar.setStyleSheet(f"""
            QPushButton {{
                background: {CINZA}; color: {BRANCO};
                border-radius: 10px; font-size: 14px; font-weight: bold; border: none;
            }}
            QPushButton:enabled {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {VERDE}, stop:1 #25C992);
            }}
            QPushButton:enabled:hover {{ background: {VERDE_HOVER}; }}
            QPushButton:enabled:pressed {{ background: #0F6E56; }}
        """)
        self.btn_iniciar.clicked.connect(self._iniciar_restauracao)
        self.restore_layout.addWidget(self.btn_iniciar)

        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setStyleSheet(f"font-size: 12px; color: {VERDE}; border: none;")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.setVisible(False)
        self.restore_layout.addWidget(self.lbl_resultado)

    # ── Lógica de seleção ─────────────────────────────────────────────────────
    def _selecionar_todos(self):
        for linha in self._linhas_arquivo:
            linha.selecionar_todos(True)
        self._atualizar_contagem()
        self._atualizar_botao_iniciar()
        self._atualizar_preview()

    def _desmarcar_todos(self):
        for linha in self._linhas_arquivo:
            linha.selecionar_todos(False)
        self._atualizar_contagem()
        self._atualizar_botao_iniciar()
        self._atualizar_preview()

    def _on_selecao_alterada(self):
        self._atualizar_contagem()
        self._atualizar_botao_iniciar()
        self._atualizar_preview()

    def _atualizar_contagem(self):
        total = sum(l.total_itens() for l in self._linhas_arquivo)
        sel   = sum(l.total_selecionados() for l in self._linhas_arquivo)
        self._lbl_contagem.setText(f"{sel} de {total} arquivo(s) selecionado(s)")
        self._lbl_contagem.setVisible(True)

    def _atualizar_botao_iniciar(self):
        sel          = sum(l.total_selecionados() for l in self._linhas_arquivo)
        conflitos_ok = (not self.conflitos) or (len(self.decisoes) >= len(self.conflitos))
        self.btn_iniciar.setEnabled(sel > 0 and conflitos_ok)

    def _arquivos_selecionados(self):
        nomes = set()
        for linha in self._linhas_arquivo:
            for n in linha.nomes_selecionados():
                nomes.add(n)
        return [arq for arq in self.arquivos if arq["nome"] in nomes]

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _on_usuario(self, matricula, nome):
        self.matricula = matricula
        self.lbl_matricula.setText(f"Matrícula: {matricula}  ·  {nome}")
        self.badge.setText("✓  Backup encontrado")
        self.badge.setVisible(True)

    def _on_erro(self, msg):
        self.lbl_matricula.setStyleSheet(f"font-size: 12px; color: #C0392B; border: none;")
        self.lbl_matricula.setText(f"Erro: {msg}")

    def _preencher_info(self, arquivos):
        self.arquivos = arquivos

        por_pasta = {}
        for arq in arquivos:
            pasta = arq.get("pasta_relativa", "") or ""
            por_pasta.setdefault(pasta, []).append({
                "nome": arq["nome"],
                "tipo": arq.get("tipo", "Outros"),
            })

        ORDEM = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]
        def _chave_pasta(p):
            raiz = p.replace("\\", "/").split("/")[0]
            try:    return (0, ORDEM.index(raiz), p)
            except: return (1, 0, p)

        for i, pasta in enumerate(sorted(por_pasta.keys(), key=_chave_pasta)):
            linha = LinhaPasta(pasta, por_pasta[pasta], on_selecao_alterada=self._on_selecao_alterada)
            self._linhas_arquivo.append(linha)
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"color: {BORDA}; background: {BORDA}; max-height: 1px; border: none;")
                self.scroll_layout.addWidget(sep)
            self.scroll_layout.addWidget(linha)

        self.btn_sel_todos.setVisible(True)
        self.btn_desm_todos.setVisible(True)
        self._atualizar_contagem()

        conflitos_preview = detectar_conflitos(arquivos) if not self.conflitos else self.conflitos
        preview = gerar_preview(arquivos, conflitos_preview)
        self._preencher_preview(preview)

    def _mostrar_conflitos(self, conflitos):
        self.conflitos = conflitos
        if not conflitos:
            self._atualizar_botao_iniciar()
            return

        self.conflitos_widget.setVisible(True)

        header = QLabel(f"⚠  {len(conflitos)} conflito(s) — arquivos já existem na sua pasta")
        header.setStyleSheet(f"""
            font-size: 13px; font-weight: bold; color: #7D4100;
            background: #FFF3E0; border-radius: 8px; border: 1px solid #FFCC80;
            padding: 8px 12px;
        """)
        self.conflitos_layout.addWidget(header)

        for caminho in conflitos:
            nome_arq = os.path.basename(caminho)

            item = QFrame()
            item.setStyleSheet("background: #FFFBF0; border-radius: 10px; border: 1px solid #FFE0A0;")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(14, 10, 14, 10)
            item_layout.setSpacing(8)

            lbl_nome = QLabel(f"📄  {nome_arq}")
            lbl_nome.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {TEXTO_PRIM}; border: none;"
            )
            item_layout.addWidget(lbl_nome)

            btns = QWidget()
            btns.setStyleSheet("background: transparent; border: none;")
            btns_layout = QHBoxLayout(btns)
            btns_layout.setContentsMargins(0, 0, 0, 0)
            btns_layout.setSpacing(8)

            btn_manter = QPushButton("Manter o atual")
            btn_manter.setFixedHeight(30)
            btn_manter.setCursor(Qt.PointingHandCursor)
            btn_manter.setStyleSheet(f"""
                QPushButton {{ background: {BRANCO}; color: {TEXTO_PRIM};
                               border-radius: 7px; border: 1px solid {BORDA}; font-size: 12px; }}
                QPushButton:hover {{ background: #EAF7DE; border-color: #7AAF45; }}
            """)

            btn_subst = QPushButton("Substituir pelo backup")
            btn_subst.setFixedHeight(30)
            btn_subst.setCursor(Qt.PointingHandCursor)
            btn_subst.setStyleSheet(f"""
                QPushButton {{ background: {BRANCO}; color: {TEXTO_PRIM};
                               border-radius: 7px; border: 1px solid {BORDA}; font-size: 12px; }}
                QPushButton:hover {{ background: #E6F1FB; border-color: #5B9FD8; }}
            """)

            btns_layout.addWidget(btn_manter)
            btns_layout.addWidget(btn_subst)
            btns_layout.addStretch()
            item_layout.addWidget(btns)
            self.conflitos_layout.addWidget(item)

            def fazer_escolha(escolha, c=caminho, bm=btn_manter, bs=btn_subst):
                self.decisoes[c] = escolha
                estilo_verde  = f"QPushButton {{ background: #DFF2CC; color: #3B6D11; border-radius: 7px; border: 1px solid #7AAF45; font-size: 12px; font-weight: bold; }}"
                estilo_azul   = f"QPushButton {{ background: #D4EAFB; color: #185FA5; border-radius: 7px; border: 1px solid #5B9FD8; font-size: 12px; font-weight: bold; }}"
                estilo_normal = f"QPushButton {{ background: {BRANCO}; color: {TEXTO_PRIM}; border-radius: 7px; border: 1px solid {BORDA}; font-size: 12px; }} QPushButton:hover {{ background: #F5F5F5; }}"
                if escolha == "manter":
                    bm.setStyleSheet(estilo_verde); bs.setStyleSheet(estilo_normal)
                else:
                    bs.setStyleSheet(estilo_azul);  bm.setStyleSheet(estilo_normal)
                self._atualizar_botao_iniciar()

            btn_manter.clicked.connect(lambda _, c=caminho: fazer_escolha("manter", c))
            btn_subst.clicked.connect(lambda _, c=caminho: fazer_escolha("substituir", c))

    def _iniciar_restauracao(self):
        arquivos_para_restaurar = self._arquivos_selecionados()
        if not arquivos_para_restaurar:
            return
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText("Restaurando...")
        self.worker_restaurar = WorkerRestaurar(arquivos_para_restaurar, self.decisoes, self.sinais)
        self.worker_restaurar.start()

    def _atualizar_progresso(self, pct, nome_arquivo):
        self.barra.setValue(pct)
        self.lbl_pct.setText(f"{pct}%")
        self.lbl_prog.setText(f"Copiando: {nome_arquivo}")

    def _finalizar(self, resultado):
        r = resultado

        salvar_log(r, self.arquivos, self.matricula)

        if r.get("rollback"):
            self.barra.setValue(0)
            self.lbl_pct.setText("0%")
            self.lbl_prog.setText("Operação cancelada")
            self.btn_iniciar.setEnabled(True)
            self.btn_iniciar.setText("Tentar novamente")
            self.lbl_resultado.setVisible(True)
            self.lbl_resultado.setStyleSheet("font-size: 12px; color: #C0392B; border: none;")
            self.lbl_resultado.setText(
                f"⚠  Erro durante a restauração — operação desfeita.\n"
                f"Nenhum arquivo foi alterado. O backup permanece intacto.\n"
                f"Detalhe: {r['erro_msg']}"
            )
            return

        self.barra.setValue(100)
        self.lbl_pct.setText("100%")
        self.lbl_prog.setText("Concluído")
        self.btn_iniciar.setText("✓  Restauração concluída")
        self.lbl_resultado.setVisible(True)
        self.lbl_resultado.setStyleSheet(f"font-size: 12px; color: {VERDE}; border: none;")
        self.lbl_resultado.setText(
            f"✔  {r['restaurados']} arquivo(s) restaurado(s)  ·  "
            f"{r['ignorados']} ignorado(s)  ·  "
            f"{r['erros']} erro(s)\n"
            f"Chamado registrado: #{r['chamado']}"
        )
