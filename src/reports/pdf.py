"""PDF com gráficos vetoriais convertidos em PNG na memória, portátil entre SOs."""

from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
import threading
import numpy as np
import pandas as pd
import reportlab
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from ..analise import PARAMETROS

_LOCK = threading.RLock()


def estilos():
    # Vera acompanha ReportLab; não depende de fontes instaladas no Windows/Linux.
    pasta = Path(reportlab.__file__).parent / "fonts"
    with _LOCK:
        if "VeraLocal" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("VeraLocal", str(pasta / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont("VeraLocalBold", str(pasta / "VeraBd.ttf")))
    return {
        "titulo": ParagraphStyle(
            "titulo", fontName="VeraLocalBold", fontSize=17, leading=22, spaceAfter=14
        ),
        "secao": ParagraphStyle(
            "secao",
            fontName="VeraLocalBold",
            fontSize=12,
            leading=16,
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "texto": ParagraphStyle(
            "texto", fontName="VeraLocal", fontSize=9, leading=13, spaceAfter=7
        ),
    }


def paragrafo(texto, estilo):
    texto = str(texto).replace("β", "beta").replace("⁰", "0").replace("⁺", "+")
    texto = (
        texto.replace("→", " -> ")
        .replace("≥", ">=")
        .replace("–", "-")
        .replace("—", "-")
    )
    return Paragraph(escape(texto).replace("\n", "<br/>"), estilo)


def finalizar(elementos, estilo):
    memoria = BytesIO()

    def rodape(canvas, documento):
        canvas.setFont("VeraLocal", 8)
        canvas.drawString(45, 25, "Uso médico experimental | documento confidencial")
        canvas.drawRightString(A4[0] - 45, 25, str(documento.page))

    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        leftMargin=45,
        rightMargin=45,
        topMargin=45,
        bottomMargin=45,
        title="Relatório experimental de acompanhamento",
        author="Protótipo de pesquisa",
    )
    documento.build(elementos, onFirstPage=rodape, onLaterPages=rodape)
    return memoria.getvalue()


def documento_pdf(titulo, texto):
    e = estilos()
    elementos = [paragrafo(titulo, e["titulo"])]
    elementos.extend(
        paragrafo(linha, e["texto"]) for linha in texto.splitlines() if linha
    )
    return finalizar(elementos, e)


def grafico_exame(exames, parametro, referencias=None):
    nome, unidade = PARAMETROS[parametro]
    figura = Figure(figsize=(8, 2.8), dpi=140)
    FigureCanvasAgg(figura)
    eixo = figura.subplots()
    eixo.plot(exames.data_coleta, exames[parametro], "o-", color="#176c78")
    if referencias is not None:
        referencia = referencias.set_index("parametro").loc[parametro]
        if pd.notna(referencia.min_laboratorio) and pd.notna(
            referencia.max_laboratorio
        ):
            eixo.axhspan(
                referencia.min_laboratorio,
                referencia.max_laboratorio,
                color="#b0b8c4",
                alpha=0.25,
                label="Faixa informada do laudo atual",
            )
            eixo.legend(fontsize=7)
    eixo.set_ylabel(f"{nome} ({unidade})")
    eixo.set_xlabel("Data da coleta")
    eixo.grid(alpha=0.2)
    figura.autofmt_xdate(rotation=25)
    figura.tight_layout()
    imagem = BytesIO()
    figura.savefig(imagem, format="png")
    imagem.seek(0)
    return imagem


def tabela_pdf(cabecalho, linhas, e, larguras=None):
    dados = [[paragrafo(c, e["texto"]) for c in cabecalho]]
    dados += [[paragrafo(c, e["texto"]) for c in linha] for linha in linhas]
    tabela = Table(dados, colWidths=larguras, repeatRows=1, hAlign="LEFT")
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8ed")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c4cbd0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return tabela


def relatorio_pdf(
    paciente,
    exames,
    comparacao,
    referencias,
    crises,
    comentarios="",
    conduta="",
    identificacao=False,
    risco=None,
    explicacoes=None,
    sintese="",
    contexto="",
    alertas=(),
):
    e = estilos()
    elementos = [paragrafo("Acompanhamento da doença falciforme", e["titulo"])]

    def titulo(texto):
        elementos.append(paragrafo(texto, e["secao"]))

    def texto(conteudo):
        elementos.append(paragrafo(conteudo, e["texto"]))

    texto(
        "Versão 0.3 | suporte experimental ao médico. Não constitui diagnóstico, prescrição ou sistema clínico validado."
    )
    texto("Gerado em " + datetime.now().astimezone().isoformat(timespec="seconds"))
    titulo("Paciente e contexto")
    texto(
        "Nome: "
        + (
            paciente.nome
            if identificacao and paciente.nome
            else "Identificação omitida"
        )
    )
    for rotulo, valor in [
        ("Idade (anos)", paciente.idade),
        ("Peso (kg)", paciente.peso_kg),
        ("Altura (cm)", paciente.altura_cm),
        ("Sexo informado", paciente.sexo),
        ("Subtipo confirmado", paciente.subtipo),
    ]:
        texto(f"{rotulo}: {valor if valor is not None else 'Não informado'}")
    texto(
        f"{paciente.cid_versao}: {paciente.cid_codigo or 'Não informada'} | {paciente.cid_descricao}"
    )
    texto(
        "CID transcrita pelo médico, sem confirmação diagnóstica ou consulta automática a catálogo. Idade, peso e altura não geram faixas automáticas."
    )
    texto(contexto)
    titulo("Sinais atuais registrados")
    if alertas:
        for regra, mensagem, fonte in alertas:
            texto(f"{regra}: {mensagem} ({fonte})")
    else:
        texto(
            "Nenhum alerta acionado pelas respostas registradas. Isso não exclui risco ou urgência."
        )
    titulo("Probabilidade e limites")
    if risco is None:
        texto(
            "Probabilidade não calculada: não há modelo treinado compatível ativo nesta sessão. Isso não equivale a risco zero ou a baixo risco. Não foram inventados percentuais."
        )
        texto(
            "SHAP e LIME não executados na ausência de modelo. A análise abaixo é descritiva."
        )
    else:
        texto(
            f"Estimativa experimental do modelo: {100 * risco['probabilidade']:.1f}%. Horizonte: {risco['horizonte']} dias após {risco['t0']}. Modelo: {risco['modelo']}."
        )
        texto(
            "Probabilidade bruta, sem recalibração adicional. A validação interna e o Brier não garantem calibração nem utilidade clínica. Não confirma que uma crise ocorrerá."
        )
        texto(
            "Somente dados até T0 são usados. O nome e a CID livre não são features. A avaliação abaixo não é validação externa."
        )
        texto(str(risco.get("metricas", {})))
    titulo("Qualidade dos dados")
    total = len(exames) * len(PARAMETROS)
    presentes = int(exames[list(PARAMETROS)].notna().sum().sum())
    texto(
        f"Coletas: {len(exames)}. Resultados presentes: {presentes}/{total}. Ausências não são zeros. Período: {exames.data_coleta.min().date()} a {exames.data_coleta.max().date()}."
    )
    titulo("Histórico de crises registrado pelo médico")
    if crises.empty:
        texto(
            "Nenhum evento registrado nesta sessão. Isso não comprova ausência de crises."
        )
    else:
        linhas = []
        for _, r in crises.iterrows():
            linhas.append(
                [
                    f"{r.inicio} a {r.fim} ({r.precisao})",
                    r.tipo,
                    r.atendimento,
                    f"{r.fonte}; confirmado: {'Sim' if r.confirmado else 'Não'}",
                ]
            )
        elementos.append(
            tabela_pdf(
                ["Período", "Tipo", "Atendimento", "Fonte"],
                linhas,
                e,
                [130, 105, 105, 165],
            )
        )
    titulo("Evolução laboratorial")
    texto(
        "Linhas entre pontos são apenas visuais. A direção numérica não determina melhora ou piora. A faixa do laudo atual pode não se aplicar às coletas antigas."
    )
    for parametro, (nome, unidade) in PARAMETROS.items():
        if not exames[parametro].notna().any():
            continue
        r = comparacao.set_index("parametro").loc[parametro]
        elementos.append(
            KeepTogether(
                [
                    paragrafo(nome, e["secao"]),
                    Image(
                        grafico_exame(exames, parametro, referencias),
                        width=500,
                        height=175,
                    ),
                    paragrafo(r.explicacao, e["texto"]),
                ]
            )
        )
    if explicacoes:
        titulo("Explicações do modelo")
        texto(
            "Contribuições descrevem o modelo e não demonstram causalidade. Pesos LIME e valores SHAP têm escalas distintas."
        )
        for metodo in ("shap", "lime"):
            valores = explicacoes[metodo]
            linhas = [
                [r["variavel"], f"{r['contribuicao']:+.5f}"] for r in valores[:10]
            ]
            elementos.append(
                tabela_pdf([metodo.upper(), "Contribuição"], linhas, e, [350, 155])
            )
        texto("Concordância e fidelidade: " + str(explicacoes["comparacao"]))
    if sintese:
        titulo("Trechos documentais conferidos")
        for linha in sintese.splitlines():
            texto(linha)
    titulo("Comentários do médico")
    texto(comentarios or "Não preenchidos.")
    titulo("Conduta e orientações registradas pelo médico")
    texto(
        conduta
        or "Não preenchidas. O software não gera prescrição ou orientação terapêutica individualizada."
    )
    texto(
        "O conteúdo desta seção foi digitado pelo profissional; não representa recomendação produzida pelo modelo."
    )
    return finalizar(elementos, e)
