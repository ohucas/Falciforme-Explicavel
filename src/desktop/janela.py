"""Primeira interface nativa de importação, revisão, comparação e PDF."""

from pathlib import Path
import sys
import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QStackedWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QCheckBox,
    QMessageBox,
    QPlainTextEdit,
    QHeaderView,
    QSplitter,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from ..documentos import ler_documento, candidatos, montar_tabela
from ..preenchimento import sugerir_preenchimento
from ..analise import PARAMETROS, SUBTIPOS, comparar, referencias_vazias, validar_exames
from ..paciente import Paciente, validar_paciente
from ..reports.pdf import relatorio_pdf


class Leitura(QThread):
    concluida = Signal(object, object)

    def __init__(self, caminhos):
        super().__init__()
        self.caminhos = caminhos

    def run(self):
        documentos, avisos = [], []
        for indice, caminho in enumerate(self.caminhos, 1):
            identificador = f"Documento {indice}"
            try:
                if Path(caminho).stat().st_size > 5_000_000:
                    raise ValueError("Arquivo excede 5 MB.")
                doc = ler_documento(Path(caminho).read_bytes(), caminho, identificador)
                dados = sugerir_preenchimento(doc, candidatos(doc))
                documentos.append((doc, dados))
                avisos.extend(f"{identificador}: {v}" for v in doc["avisos"])
            except (OSError, ValueError) as erro:
                avisos.append(f"{identificador}: {erro}")
        self.concluida.emit(documentos, avisos)


class Janela(QMainWindow):
    campos = [
        "usar",
        "documento",
        "pagina",
        "parametro",
        "valor_confirmado",
        "unidade_confirmada",
        "data_coleta",
        "origem_data",
    ]
    titulos = [
        "Usar",
        "Documento",
        "Página",
        "Parâmetro",
        "Valor",
        "Unidade",
        "Coleta AAAA-MM-DD",
        "Origem da data",
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Falciforme Explicável — acompanhamento local")
        self.resize(1320, 850)
        self.setMinimumSize(1000, 650)
        self.setWindowIcon(QIcon(str(Path(__file__).parents[2] / "assets/icone.png")))
        self.documentos = []
        self.dados = pd.DataFrame()
        self.exames = None
        self.comparacao = None
        self.tarefa = None
        self.atualizando = False
        raiz = QWidget()
        self.setCentralWidget(raiz)
        layout = QHBoxLayout(raiz)
        self.menu = QListWidget()
        self.menu.setFixedWidth(235)
        self.menu.addItems(
            [
                "1  Paciente",
                "2  Importar documentos",
                "3  Conferir resultados",
                "4  Evolução",
                "5  Relatório",
            ]
        )
        self.paginas = QStackedWidget()
        layout.addWidget(self.menu)
        layout.addWidget(self.paginas, 1)
        self.menu.currentRowChanged.connect(self.paginas.setCurrentIndex)
        self.paciente_ui()
        self.importacao_ui()
        self.revisao_ui()
        self.evolucao_ui()
        self.relatorio_ui()
        self.menu.setCurrentRow(0)
        self.statusBar().showMessage(
            "Sessão local • sem login • sem modelo de risco integrado"
        )
        self.setStyleSheet("""
            QWidget {font-family: 'Segoe UI', sans-serif; font-size: 14px; color:#203448;}
            QMainWindow, QStackedWidget {background:#f4f7fb;}
            QListWidget {background:#122f4c; color:white; border:0; padding:16px 6px;}
            QListWidget::item {padding:16px 8px; border-radius:6px;}
            QListWidget::item:selected {background:#246c96;}
            QPushButton {background:#156d88; color:white; border:0; border-radius:6px; padding:12px 18px;}
            QPushButton:disabled {background:#bdc9d2; color:#324b60;}
            QLineEdit,QComboBox,QPlainTextEdit,QTableWidget {background:white; border:1px solid #cbd5df; padding:7px;}
            QHeaderView::section {background:#e5edf4; padding:8px; border:0;}
            QLabel#titulo {font-size:25px; font-weight:600; color:#153e5c;}
        """)

    def pagina(self, titulo, descricao):
        widget = QWidget()
        caixa = QVBoxLayout(widget)
        caixa.setContentsMargins(28, 24, 28, 24)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("titulo")
        caixa.addWidget(rotulo)
        texto = QLabel(descricao)
        texto.setWordWrap(True)
        caixa.addWidget(texto)
        self.paginas.addWidget(widget)
        return caixa

    def ir(self, indice):
        self.menu.setCurrentRow(indice)

    def paciente_ui(self):
        caixa = self.pagina(
            "Identificação do atendimento",
            "Preencha apenas o necessário. Identificação opcional no PDF; não usada em treinamento.",
        )
        formulario = QFormLayout()
        self.entradas = {}
        for chave, rotulo in [
            ("nome", "Nome opcional"),
            ("idade", "Idade em anos"),
            ("peso_kg", "Peso em kg"),
            ("altura_cm", "Altura em cm"),
        ]:
            campo = QLineEdit()
            campo.setPlaceholderText("Não informado")
            self.entradas[chave] = campo
            formulario.addRow(rotulo, campo)
        self.subtipo = QComboBox()
        self.subtipo.addItems(SUBTIPOS)
        self.subtipo.setCurrentIndex(len(SUBTIPOS) - 1)
        formulario.addRow("Subtipo informado pelo médico", self.subtipo)
        formulario.addRow(
            "Código do atendimento", QLabel("D57.0 • confirmar adequação clínica")
        )
        caixa.addLayout(formulario)
        caixa.addStretch()
        botao = QPushButton("Continuar para os documentos")
        botao.clicked.connect(lambda: self.ir(1))
        caixa.addWidget(botao)

    def importacao_ui(self):
        caixa = self.pagina(
            "Importar exames e documentos",
            "Selecione até dez documentos da mesma pessoa. A seleção substitui a importação anterior; confira as datas após a leitura.",
        )
        linha = QHBoxLayout()
        self.importar = QPushButton("Selecionar documentos")
        self.importar.clicked.connect(self.escolher_documentos)
        self.demo = QPushButton("Abrir demonstração fictícia")
        self.demo.clicked.connect(self.abrir_demo)
        linha.addWidget(self.importar)
        linha.addWidget(self.demo)
        caixa.addLayout(linha)
        self.situacao = QLabel("Nenhum documento importado.")
        self.situacao.setWordWrap(True)
        caixa.addWidget(self.situacao)
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setPlaceholderText(
            "O texto extraído aparecerá aqui e poderá ser selecionado e copiado."
        )
        caixa.addWidget(self.texto, 1)
        self.proxima = QPushButton("Conferir resultados reconhecidos")
        self.proxima.clicked.connect(lambda: self.ir(2))
        caixa.addWidget(self.proxima)

    def revisao_ui(self):
        caixa = self.pagina(
            "Conferir valores e datas",
            "Revise as linhas antes de preparar a comparação. Corrija valores e datas; unidades incompatíveis permanecem pendentes.",
        )
        self.tabela = QTableWidget(0, len(self.campos))
        self.tabela.setHorizontalHeaderLabels(self.titulos)
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tabela.itemChanged.connect(self.invalidar)
        caixa.addWidget(self.tabela, 1)
        self.revisado = QCheckBox(
            "Conferi valores, unidades, datas e que os documentos pertencem à mesma pessoa"
        )
        self.data_confirmada = QCheckBox(
            "Confirmei as datas sugeridas pelo atendimento como datas de coleta"
        )
        self.data_confirmada.hide()
        self.parcial = QCheckBox(
            "Aceito continuar sem os documentos que ficaram sem resultados selecionados"
        )
        caixa.addWidget(self.revisado)
        caixa.addWidget(self.data_confirmada)
        caixa.addWidget(self.parcial)
        self.revisado.toggled.connect(self.invalidar_resultado)
        self.data_confirmada.toggled.connect(self.invalidar_resultado)
        self.parcial.toggled.connect(self.invalidar_resultado)
        botao = QPushButton("Preparar e analisar coletas conferidas")
        botao.clicked.connect(self.analisar)
        caixa.addWidget(botao)

    def evolucao_ui(self):
        caixa = self.pagina(
            "Evolução dos exames",
            "Comparação descritiva. A direção numérica não determina melhora ou piora clínica.",
        )
        self.qualidade = QLabel(
            "Faça a importação e a conferência para visualizar a evolução."
        )
        caixa.addWidget(self.qualidade)
        self.parametro = QComboBox()
        for chave, (nome, unidade) in PARAMETROS.items():
            self.parametro.addItem(f"{nome} ({unidade})", chave)
        self.parametro.currentIndexChanged.connect(self.desenhar)
        caixa.addWidget(self.parametro)
        self.figura = Figure(figsize=(9, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figura)
        caixa.addWidget(self.canvas, 1)
        self.comentario = QLabel("")
        self.comentario.setWordWrap(True)
        caixa.addWidget(self.comentario)
        caixa.addWidget(
            QLabel(
                "Predição indisponível • ainda não há um modelo de risco treinado integrado."
            )
        )

    def relatorio_ui(self):
        caixa = self.pagina(
            "Relatório do atendimento",
            "Exporte um PDF local com gráficos e comentários. Escolha conscientemente se deseja incluir a identificação.",
        )
        self.identificar = QCheckBox("Incluir o nome informado no PDF")
        caixa.addWidget(self.identificar)
        self.observacoes = QPlainTextEdit()
        self.observacoes.setPlaceholderText(
            "Comentários do médico sobre os dados revisados"
        )
        caixa.addWidget(self.observacoes, 1)
        self.exportar = QPushButton("Salvar relatório em PDF")
        self.exportar.clicked.connect(self.salvar_pdf)
        self.exportar.setEnabled(False)
        caixa.addWidget(self.exportar)
        self.limpar = QPushButton("Encerrar atendimento e limpar sessão")
        self.limpar.clicked.connect(self.limpar_sessao)
        caixa.addWidget(self.limpar)

    def invalidar_resultado(self):
        self.exames = None
        self.comparacao = None
        self.exportar.setEnabled(False)
        self.qualidade.setText(
            "Dados ou confirmações alterados. Analise novamente na conferência."
        )
        self.desenhar()

    def invalidar(self):
        if not self.atualizando:
            self.revisado.setChecked(False)
            self.data_confirmada.setChecked(False)
            self.invalidar_resultado()

    def escolher_documentos(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar documentos",
            "",
            "Documentos (*.pdf *.docx *.txt *.png *.jpg *.jpeg)",
        )
        if not caminhos:
            return
        if len(caminhos) > 10:
            QMessageBox.warning(
                self, "Limite de arquivos", "Selecione até dez documentos."
            )
            return
        self.invalidar_resultado()
        self.importar.setEnabled(False)
        self.demo.setEnabled(False)
        self.limpar.setEnabled(False)
        self.proxima.setEnabled(False)
        self.situacao.setText(
            "Lendo documentos localmente… OCR pode levar alguns instantes."
        )
        self.tarefa = Leitura(caminhos)
        self.tarefa.concluida.connect(self.receber)
        self.tarefa.finished.connect(self.finalizar_leitura)
        self.tarefa.start()

    def finalizar_leitura(self):
        self.tarefa.caminhos = []
        self.importar.setEnabled(True)
        self.demo.setEnabled(True)
        self.limpar.setEnabled(True)
        self.proxima.setEnabled(True)

    def receber(self, documentos, avisos):
        self.documentos = documentos
        self.revisado.setChecked(False)
        self.data_confirmada.setChecked(False)
        self.parcial.setChecked(False)
        textos = []
        for doc, dados in documentos:
            textos.append(f"{doc['id']} — {len(dados)} resultado(s) reconhecido(s)")
            textos.extend(f"Página {p['pagina']}\n{p['texto']}" for p in doc["paginas"])
        self.texto.setPlainText("\n\n".join(textos))
        tabelas = [d for _, d in documentos if not d.empty]
        self.dados = (
            pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()
        )
        self.atualizando = True
        self.tabela.setRowCount(len(self.dados))
        for indice, registro in self.dados.iterrows():
            for coluna, chave in enumerate(self.campos):
                valor = registro.get(chave, "")
                item = QTableWidgetItem("" if pd.isna(valor) else str(valor))
                if chave == "usar":
                    item.setText("")
                    item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    item.setCheckState(
                        Qt.CheckState.Checked if valor else Qt.CheckState.Unchecked
                    )
                elif chave not in {
                    "valor_confirmado",
                    "unidade_confirmada",
                    "data_coleta",
                }:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabela.setItem(indice, coluna, item)
        self.atualizando = False
        atendimento = (
            not self.dados.empty
            and self.dados.origem_data.eq("atendimento — confirmar coleta").any()
        )
        self.data_confirmada.setVisible(bool(atendimento))
        resumo = [
            f"{doc['id']}: {len(dados)} reconhecido(s), {int(dados.usar.sum()) if not dados.empty else 0} pronto(s) para revisão."
            for doc, dados in documentos
        ]
        self.situacao.setText(
            "\n".join(resumo + avisos)
            or "Nenhum resultado disponível. Confira os arquivos."
        )
        self.statusBar().showMessage(
            "Leitura concluída. Confira os resultados antes de analisar."
        )

    def dados_editados(self):
        dados = self.dados.copy()
        for i in range(len(dados)):
            dados.at[i, "usar"] = (
                self.tabela.item(i, 0).checkState() == Qt.CheckState.Checked
            )
            for chave in ["valor_confirmado", "unidade_confirmada", "data_coleta"]:
                texto = self.tabela.item(i, self.campos.index(chave)).text().strip()
                if chave == "valor_confirmado":
                    try:
                        texto = (
                            float(texto.replace(",", ".")) if texto else float("nan")
                        )
                    except ValueError:
                        raise ValueError(f"Valor inválido na linha {i+1}.") from None
                dados.at[i, chave] = texto
        return dados

    def analisar(self):
        try:
            if self.tarefa is not None and self.tarefa.isRunning():
                raise ValueError("Aguarde a importação terminar antes de analisar.")
            if not self.revisado.isChecked():
                raise ValueError("Confirme a revisão dos valores, unidades e datas.")
            dados = self.dados_editados()
            if dados.empty:
                raise ValueError(
                    "Nenhum resultado disponível. Confira os avisos da importação."
                )
            usados = dados[dados.usar.eq(True)]
            pendentes = [
                doc["id"]
                for doc, _ in self.documentos
                if doc["id"] not in set(usados.documento)
            ]
            if pendentes and not self.parcial.isChecked():
                raise ValueError(
                    "Sem resultados selecionados em "
                    + ", ".join(pendentes)
                    + ". Confira ou autorize a comparação parcial."
                )
            if (
                usados.origem_data.eq("atendimento — confirmar coleta").any()
                and not self.data_confirmada.isChecked()
            ):
                raise ValueError(
                    "Confirme as datas de atendimento como coleta ou use documentos com coleta explícita."
                )
            exames = validar_exames(
                montar_tabela(dados), min_coletas=2, max_coletas=500
            )
            self.comparacao = comparar(exames)
            self.exames = exames
            preenchidos = int(exames[list(PARAMETROS)].notna().sum().sum())
            self.qualidade.setText(
                f"{len(exames)} coletas distintas • {preenchidos} resultados preenchidos • conferência concluída"
            )
            self.exportar.setEnabled(True)
            self.desenhar()
            self.ir(3)
        except ValueError as erro:
            QMessageBox.warning(self, "Confira os dados", str(erro))

    def desenhar(self):
        self.figura.clear()
        eixo = self.figura.add_subplot(111)
        if self.exames is not None:
            chave = self.parametro.currentData()
            nome, unidade = PARAMETROS[chave]
            eixo.plot(
                self.exames.data_coleta, self.exames[chave], "-o", color="#147a91"
            )
            eixo.set_ylabel(f"{nome} ({unidade})")
            eixo.set_xlabel("Data da coleta")
            eixo.grid(alpha=0.2)
            self.comentario.setText(
                self.comparacao.set_index("parametro").loc[chave, "explicacao"]
            )
        else:
            eixo.text(
                0.5,
                0.5,
                "Aguardando dados conferidos",
                ha="center",
                va="center",
                transform=eixo.transAxes,
            )
            eixo.set_axis_off()
            self.comentario.setText("")
        self.canvas.draw_idle()

    def paciente(self):
        valores = {
            "nome": self.entradas["nome"].text().strip(),
            "subtipo": self.subtipo.currentText(),
        }
        for chave in ["idade", "peso_kg", "altura_cm"]:
            texto = self.entradas[chave].text().strip()
            try:
                valores[chave] = float(texto.replace(",", ".")) if texto else None
            except ValueError:
                raise ValueError(f"Confira o campo {chave}.") from None
        return validar_paciente(Paciente(**valores))

    def salvar_pdf(self):
        if self.exames is None:
            return
        try:
            paciente = self.paciente()
            pdf = relatorio_pdf(
                paciente,
                self.exames,
                self.comparacao,
                referencias_vazias(),
                pd.DataFrame(),
                comentarios=self.observacoes.toPlainText(),
                identificacao=self.identificar.isChecked(),
            )
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar relatório", "relatorio.pdf", "PDF (*.pdf)"
            )
            if caminho:
                if not caminho.lower().endswith(".pdf"):
                    caminho += ".pdf"
                Path(caminho).write_bytes(pdf)
                self.statusBar().showMessage(
                    "PDF salvo no local escolhido. Ele pode conter dados sensíveis."
                )
        except (ValueError, OSError) as erro:
            QMessageBox.warning(self, "Não foi possível exportar", str(erro))

    def abrir_demo(self):
        texto = "\n".join(
            f"Coleta: {data}\nHemoglobina {valor} g/dL\nVCM 90 fL"
            for data, valor in [
                ("02/01/2026", "9,0"),
                ("02/04/2026", "9,2"),
                ("02/07/2026", "9,4"),
            ]
        )
        doc = ler_documento(texto.encode(), "demonstracao.txt")
        self.invalidar_resultado()
        self.receber(
            [(doc, sugerir_preenchimento(doc, candidatos(doc)))],
            ["DEMONSTRAÇÃO: dados fictícios."],
        )
        self.ir(2)

    def limpar_sessao(self):
        self.documentos = []
        self.dados = pd.DataFrame()
        self.tabela.setRowCount(0)
        self.texto.clear()
        self.observacoes.clear()
        for campo in self.entradas.values():
            campo.clear()
        self.subtipo.setCurrentIndex(len(SUBTIPOS) - 1)
        for campo in [
            self.revisado,
            self.parcial,
            self.data_confirmada,
            self.identificar,
        ]:
            campo.setChecked(False)
        self.data_confirmada.hide()
        self.situacao.setText(
            "Sessão limpa. Downloads já salvos permanecem no computador."
        )
        self.invalidar_resultado()
        self.ir(0)

    def closeEvent(self, event):
        if self.tarefa is not None and self.tarefa.isRunning():
            QMessageBox.information(
                self,
                "Leitura em andamento",
                "Aguarde a leitura terminar antes de fechar.",
            )
            event.ignore()
        else:
            event.accept()


def iniciar():
    app = QApplication(sys.argv)
    janela = Janela()
    janela.show()
    sys.exit(app.exec())
