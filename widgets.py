import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect

from estilos import (
    VERDE, CINZA, BRANCO, BORDA,
    TEXTO_PRIM, TEXTO_SEC, TEXTO_TERT,
    CINZA_LIGHT, VERDE_LIGHT,
    ITEM_BG, ITEM_CHECK_ON, ITEM_BORDA_ON,
    ICONES_EXT, ICONES_TIPO,
    icone_pasta, nome_pasta_display,
)


def _sombra(raio=12, opacidade=18):
    s = QGraphicsDropShadowEffect()
    s.setBlurRadius(raio)
    s.setOffset(0, 2)
    s.setColor(QColor(0, 0, 0, opacidade))
    return s


# ─────────────────────────────────────────────────────────────────────────────
class ItemArquivo(QWidget):
    """Linha individual de arquivo com checkbox dentro do dropdown de pasta."""

    def __init__(self, nome, tipo="Outros", selecionado=True, on_toggle=None, parent=None):
        super().__init__(parent)
        self._nome      = nome
        self._on_toggle = on_toggle
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        # Checkbox
        self.chk = QCheckBox()
        self.chk.setChecked(selecionado)
        self.chk.setStyleSheet(f"""
            QCheckBox {{ background: transparent; border: none; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border-radius: 3px;
                border: 1.5px solid {CINZA};
                background: {BRANCO};
            }}
            QCheckBox::indicator:checked {{
                background-color: {VERDE};
                border: 1.5px solid {CINZA};
            }}
        """)
        self.chk.stateChanged.connect(self._on_state)
        layout.addWidget(self.chk)

        # Ícone pela extensão do arquivo
        ext       = os.path.splitext(nome)[1].lower()
        icone_ext = ICONES_EXT.get(ext, ICONES_TIPO.get(tipo, "📄"))
        lbl_icone = QLabel(icone_ext)
        lbl_icone.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        lbl_icone.setFixedWidth(18)
        layout.addWidget(lbl_icone)

        # Nome do arquivo
        self._lbl_nome = QLabel(nome)
        self._lbl_nome.setStyleSheet(
            f"font-size: 12px; color: {TEXTO_PRIM}; background: transparent; border: none;"
        )
        layout.addWidget(self._lbl_nome, stretch=1)

        # Tipo à direita (pill discreta)
        from estilos import NOMES_PT
        tipo_str = NOMES_PT.get(tipo, tipo)
        lbl_tipo = QLabel(tipo_str)
        lbl_tipo.setStyleSheet(
            f"font-size: 9px; color: {TEXTO_TERT}; background: {CINZA_LIGHT}; "
            f"border-radius: 4px; border: none; padding: 1px 5px;"
        )
        layout.addWidget(lbl_tipo)

        self._atualizar_estilo()
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.chk.setChecked(not self.chk.isChecked())

    def _on_state(self):
        self._atualizar_estilo()
        if self._on_toggle:
            self._on_toggle()

    def _atualizar_estilo(self):
        if self.chk.isChecked():
            self.setStyleSheet(f"""
                ItemArquivo {{
                    background: {ITEM_CHECK_ON};
                    border-radius: 6px;
                    border: 1.5px solid {ITEM_BORDA_ON};
                }}
            """)
            self._lbl_nome.setStyleSheet(
                f"font-size: 12px; color: {TEXTO_PRIM}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(f"""
                ItemArquivo {{
                    background: {ITEM_BG};
                    border-radius: 6px;
                    border: 1px solid {BORDA};
                }}
            """)
            self._lbl_nome.setStyleSheet(
                f"font-size: 12px; color: {TEXTO_SEC}; background: transparent; border: none;"
            )

    def is_checked(self):
        return self.chk.isChecked()

    def set_checked(self, val):
        self.chk.blockSignals(True)
        self.chk.setChecked(val)
        self.chk.blockSignals(False)
        self._atualizar_estilo()

    def nome_arquivo(self):
        return self._nome


# ─────────────────────────────────────────────────────────────────────────────
class LinhaPasta(QWidget):
    """
    Linha expansível agrupada por PASTA.
    Mostra: ícone da pasta + nome da pasta + badge X/Y selecionados.
    Ao expandir, lista os arquivos daquela pasta para selecionar.
    """

    def __init__(self, pasta_relativa, arquivos_da_pasta, on_selecao_alterada=None, parent=None):
        super().__init__(parent)
        self._pasta               = pasta_relativa
        self._on_selecao_alterada = on_selecao_alterada
        self._itens: list[ItemArquivo] = []

        qtd    = len(arquivos_da_pasta)
        plural = "s" if qtd != 1 else ""
        icone  = icone_pasta(pasta_relativa)
        nome   = nome_pasta_display(pasta_relativa)

        self.aberto = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet(
            "QFrame { background: transparent; border-radius: 8px; border: none; }"
        )
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(8)

        # Ícone da pasta
        lbl_icone = QLabel(icone)
        lbl_icone.setFixedWidth(22)
        lbl_icone.setStyleSheet("font-size: 15px; background: transparent; border: none;")
        h_layout.addWidget(lbl_icone)

        # Coluna: nome da pasta + contagem de arquivos
        col = QWidget()
        col.setStyleSheet("background: transparent; border: none;")
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(1)

        self._lbl_nome = QLabel(nome)
        self._lbl_nome.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXTO_PRIM}; "
            f"background: transparent; border: none;"
        )
        col_layout.addWidget(self._lbl_nome)

        self._lbl_sub = QLabel(f"{qtd} arquivo{plural}")
        self._lbl_sub.setStyleSheet(
            f"font-size: 10px; color: {TEXTO_TERT}; background: transparent; border: none;"
        )
        col_layout.addWidget(self._lbl_sub)

        h_layout.addWidget(col, stretch=1)

        # Badge X/Y
        self._badge_sel = QLabel("")
        self._badge_sel.setStyleSheet(
            f"color: {TEXTO_TERT}; font-size: 10px; font-weight: bold; "
            f"background: {CINZA_LIGHT}; border-radius: 8px; "
            f"border: 1px solid {BORDA}; padding: 1px 6px;"
        )
        h_layout.addWidget(self._badge_sel)

        # Seta expansão
        self.seta = QLabel("›")
        self.seta.setStyleSheet(
            f"color: {TEXTO_TERT}; font-size: 16px; background: transparent; border: none;"
        )
        h_layout.addWidget(self.seta)

        # ── Lista expansível ──────────────────────────────────────────────────
        self.lista_widget = QFrame()
        self.lista_widget.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.lista_layout = QVBoxLayout(self.lista_widget)
        self.lista_layout.setContentsMargins(12, 4, 4, 6)
        self.lista_layout.setSpacing(3)

        for arq in arquivos_da_pasta:
            item = ItemArquivo(
                arq["nome"],
                tipo=arq.get("tipo", "Outros"),
                selecionado=True,
                on_toggle=self._on_item_toggle,
            )
            self._itens.append(item)
            self.lista_layout.addWidget(item)

        self.lista_widget.setVisible(False)
        self._atualizar_badge()

        layout.addWidget(self.header)
        layout.addWidget(self.lista_widget)

        self.header.mousePressEvent = self._toggle
        self.header.enterEvent      = self._entrar
        self.header.leaveEvent      = self._sair

    def _toggle(self, event=None):
        self.aberto = not self.aberto
        self.lista_widget.setVisible(self.aberto)
        self.seta.setText("⌄" if self.aberto else "›")

    def _entrar(self, event):
        self.header.setStyleSheet(
            f"QFrame {{ background: {CINZA_LIGHT}; border-radius: 8px; border: none; }}"
        )

    def _sair(self, event):
        self.header.setStyleSheet(
            "QFrame { background: transparent; border-radius: 8px; border: none; }"
        )

    def _on_item_toggle(self):
        self._atualizar_badge()
        if self._on_selecao_alterada:
            self._on_selecao_alterada()

    def _atualizar_badge(self):
        sel   = sum(1 for it in self._itens if it.is_checked())
        total = len(self._itens)
        self._badge_sel.setText(f"{sel}/{total}")

        if sel > 0:
            self._badge_sel.setStyleSheet(
                f"color: {VERDE}; font-size: 10px; font-weight: bold; "
                f"background: {VERDE_LIGHT}; border-radius: 8px; "
                f"border: 1px solid {ITEM_BORDA_ON}; padding: 1px 6px;"
            )
        else:
            self._badge_sel.setStyleSheet(
                f"color: {TEXTO_TERT}; font-size: 10px; font-weight: bold; "
                f"background: {CINZA_LIGHT}; border-radius: 8px; "
                f"border: 1px solid {BORDA}; padding: 1px 6px;"
            )

    def selecionar_todos(self, val: bool):
        for it in self._itens:
            it.set_checked(val)
        self._atualizar_badge()

    def total_itens(self):
        return len(self._itens)

    def total_selecionados(self):
        return sum(1 for it in self._itens if it.is_checked())

    def nomes_selecionados(self) -> list:
        return [it.nome_arquivo() for it in self._itens if it.is_checked()]


# Mantém compatibilidade: LinhaArquivo agora é apenas um alias de LinhaPasta
LinhaArquivo = LinhaPasta
