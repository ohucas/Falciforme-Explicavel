from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.analise import (
    PARAMETROS,
    SUBTIPOS,
    FONTES,
    vazio,
    referencias_vazias,
    comparar,
    validar_referencias,
    sinais_alerta,
)
from src.paciente import Paciente, validar_paciente, contexto_numerico
from src.historico import (
    ATENDIMENTOS,
    TIPOS,
    atributos_temporais,
    contagem_confirmada,
    crises_vazias,
    resumo_anual,
    validar_crises,
    validar_historico,
)
from src.importacao_ui import entrada_documentos
from src.reports.pdf import relatorio_pdf

RAIZ = Path(__file__).resolve().parent
ICONE = RAIZ / "assets" / "icone.png"

st.set_page_config(
    page_title="Falciforme Explicável",
    page_icon=str(ICONE) if ICONE.is_file() else "🩸",
    layout="wide",
)
st.title("Falciforme Explicável")
st.caption("Acompanhamento longitudinal e apoio à avaliação médica")
st.warning(
    "Protótipo de pesquisa: não realiza diagnóstico, não prescreve, não recomenda alterações de tratamento e não é sistema clínico validado. Sintomas atuais exigem avaliação clínica independentemente dos exames antigos."
)
if "epoca" not in st.session_state:
    st.session_state.epoca = 0
    st.session_state.modo_demo = False
chave = str(st.session_state.epoca)
coluna_a, coluna_b = st.columns(2)
if coluna_a.button("Carregar demonstração fictícia"):
    st.session_state.epoca += 1
    st.session_state.modo_demo = True
    st.rerun()
if coluna_b.button("Limpar sessão e começar em branco"):
    proxima = st.session_state.epoca + 1
    st.session_state.clear()
    st.session_state.epoca = proxima
    st.session_state.modo_demo = False
    st.rerun()
demo = st.session_state.modo_demo
if demo:
    st.info(
        "DEMONSTRAÇÃO FICTÍCIA: nenhum dado representa uma pessoa real. Não há modelo de risco de demonstração."
    )
st.caption(
    "Os dados são utilizados nesta sessão de atendimento, sem cadastro permanente. Guarde o PDF com confidencialidade. Limpar a sessão não apaga arquivos já baixados."
)
abas = st.tabs(
    [
        "Paciente",
        "CID e contexto clínico",
        "Histórico de crises",
        "Exames e documentos",
        "Análise e relatório",
    ]
)
with abas[0]:
    st.subheader("Identificação temporária para o relatório")
    st.caption("Preenchimento apenas nesta sessão, sem login ou cadastro permanente.")
    nome = st.text_input(
        "Nome do paciente (opcional)",
        value="Paciente fictício" if demo else "",
        max_chars=160,
        key="nome" + chave,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        idade = st.number_input(
            "Idade em anos",
            min_value=0.0,
            max_value=120.0,
            value=30.0 if demo else None,
            key="idade" + chave,
        )
    with c2:
        peso = st.number_input(
            "Peso em kg",
            min_value=0.1,
            max_value=500.0,
            value=65.0 if demo else None,
            key="peso" + chave,
        )
    with c3:
        altura = st.number_input(
            "Altura em cm",
            min_value=1.0,
            max_value=260.0,
            value=170.0 if demo else None,
            key="altura" + chave,
        )
    sexo = st.selectbox(
        "Sexo informado",
        ["Não informado", "Feminino", "Masculino", "Outro"],
        key="sexo" + chave,
    )
    subtipo = st.selectbox(
        "Subtipo confirmado", SUBTIPOS, index=len(SUBTIPOS) - 1, key="subtipo" + chave
    )
    st.caption(
        "Deixe desconhecidos em branco. Confira as unidades e os valores informados. Não há ajuste automático de normalidade por idade, peso, altura ou subtipo."
    )
with abas[1]:
    versao_cid = "CID-10"
    codigo_cid = "D57.0"
    descricao_cid = "Anemia falciforme com crise"
    st.subheader("CID D57.0 — Anemia falciforme com crise")
    st.caption(
        "Escopo exclusivo desta aplicação. O médico deve confirmar a adequação "
        "do código ao caso. O sistema não atribui diagnóstico nem conclui "
        "que exista uma crise atual a partir deste campo."
    )
    hidroxiureia = st.selectbox(
        "Uso de hidroxiureia",
        ["Não informado", "Sim", "Não"],
        key="hidroxiureia" + chave,
    )
    contexto = st.text_area(
        "Tratamento, transfusões, complicações e intercorrências relevantes",
        key="contexto" + chave,
    )
    st.subheader("Sinais atuais registrados pelo médico")
    temperatura = st.number_input(
        "Temperatura atual medida em °C (opcional)",
        min_value=30.0,
        max_value=45.0,
        value=None,
        key="temperatura" + chave,
    )
    sintomas = st.multiselect(
        "Sinais de alerta",
        [
            "Falta de ar",
            "Dor no peito",
            "Fraqueza súbita ou dificuldade para falar",
            "Dor intensa não controlada",
        ],
        key="sintomas" + chave,
    )
    alertas = sinais_alerta(temperatura, sintomas)
    for _, mensagem, _ in alertas:
        st.error(mensagem)
    st.caption(
        "Os avisos são regras de segurança e não estimativas de risco. Sintomas históricos de relatórios não são preenchidos como sintomas atuais."
    )
    with st.expander("Fontes dos avisos"):
        for identificador, (titulo, url) in FONTES.items():
            st.markdown(f"{identificador}: [{titulo}]({url})")
with abas[2]:
    st.subheader("Eventos registrados pelo médico")
    st.write(
        "Uma linha por crise. Informe ano e, quando conhecidos, mês e dia. Deixe dia ou mês desconhecido em branco; não será inventada uma data."
    )
    tabela_crises = st.data_editor(
        crises_vazias(),
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "ano": st.column_config.NumberColumn("Ano", format="%d"),
            "mes": st.column_config.NumberColumn(
                "Mês, se conhecido", min_value=1, max_value=12, format="%d"
            ),
            "dia": st.column_config.NumberColumn(
                "Dia, se conhecido", min_value=1, max_value=31, format="%d"
            ),
            "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS),
            "atendimento": st.column_config.SelectboxColumn(
                "Atendimento", options=ATENDIMENTOS
            ),
            "fonte": st.column_config.TextColumn("Fonte ou documento"),
            "confirmado": st.column_config.CheckboxColumn(
                "Confirmado pelo médico", default=False
            ),
        },
        key="crises" + chave,
        width="stretch",
    )
    cobertura = st.checkbox(
        "Revisei a cobertura completa dos 365 dias anteriores à última coleta, inclusive a ausência de eventos",
        key="cobertura" + chave,
    )
    st.caption(
        "A confirmação exige fonte. Registros sem confirmação permanecem no relatório, e ficam diferenciados dos eventos confirmados. Ano incompleto não deve ser interpretado como melhora em relação a um ano inteiro."
    )
    try:
        crises = validar_crises(tabela_crises)
        st.dataframe(resumo_anual(crises), hide_index=True)
    except ValueError as erro:
        crises = None
        st.error(str(erro))
with abas[3]:
    st.subheader("Exames e documentos")
    st.write(
        "Preserva a entrada de três exames e aceita de duas a 500 coletas distintas. Ausências ficam vazias, nunca como zero."
    )
    with st.expander("Unidades obrigatórias"):
        st.dataframe(
            pd.DataFrame(
                [
                    {"coluna": p, "medida": n, "unidade": u}
                    for p, (n, u) in PARAMETROS.items()
                ]
            ),
            hide_index=True,
        )
        st.write(
            "Plaquetas em mil/µL: 300 representa 300 mil/µL. Leucócitos em células/µL. RDW é RDW-CV, não RDW-SD. Não há conversão automática de unidades."
        )
        st.download_button(
            "Baixar estrutura CSV",
            vazio().iloc[:0].to_csv(index=False).encode(),
            "exames_modelo.csv",
            "text/csv",
        )
    modo = st.radio(
        "Entrada",
        ["Digitar na tabela", "Importar CSV", "Ler relatórios"],
        horizontal=True,
        key="modo" + chave,
    )
    base = pd.read_csv(RAIZ / "exemplos/tres_exames_ficticios.csv") if demo else vazio()
    proveniencia = None
    if modo == "Ler relatórios":
        base, proveniencia = entrada_documentos(chave)
    elif modo == "Importar CSV":
        separador = st.selectbox("Separador do CSV", [",", ";"], key="sep" + chave)
        decimal = st.selectbox("Separador decimal", [".", ","], key="dec" + chave)
        arquivo = st.file_uploader(
            "CSV laboratorial sem identificadores pessoais",
            type=["csv"],
            key="csv" + chave,
        )
        if arquivo:
            try:
                if arquivo.size > 2_000_000:
                    raise ValueError("Limite de 2 MB para o CSV.")
                base = pd.read_csv(
                    BytesIO(arquivo.getvalue()),
                    sep=separador,
                    decimal=decimal,
                    encoding="utf-8-sig",
                )
            except (ValueError, UnicodeError) as erro:
                st.error(str(erro))
                st.stop()
    versao_base = hashlib.sha256(
        (modo + base.to_json(date_format="iso")).encode()
    ).hexdigest()[:12]
    st.caption(
        "Data da coleta: AAAA-MM-DD ou DD/MM/AAAA. Linhas inteiramente vazias não são consideradas exames."
    )
    exames_editados = st.data_editor(
        base,
        num_rows="dynamic",
        hide_index=True,
        key="exames" + chave + versao_base,
        width="stretch",
    )
    st.markdown("**Referências opcionais do laudo**")
    referencias = st.data_editor(
        referencias_vazias(),
        disabled=["parametro"],
        hide_index=True,
        key="refs" + chave,
        width="stretch",
    )
    basal_ok = st.checkbox(
        "Os basais preenchidos foram revisados pelo médico", key="basal" + chave
    )
    conferencia = st.checkbox(
        "Conferi os dados do paciente, a adequação do CID D57.0, as crises, datas, unidades, valores e referências; os documentos pertencem à mesma pessoa",
        key="conf" + chave,
    )
    if st.button("Analisar dados conferidos", key="analisar" + chave):
        if not conferencia:
            st.error("Confirme a conferência médica antes de analisar.")
        elif modo == "Ler relatórios" and (
            proveniencia is None or not proveniencia.get("confirmado", False)
        ):
            st.error(
                "A importação documental ainda não foi confirmada. Marque usar nos "
                "resultados, confira as datas de coleta e confirme a conferência "
                "documental e as datas sugeridas pelo atendimento, quando houver. Corrija também os avisos exibidos acima."
            )
        elif crises is None:
            st.error("Corrija o histórico de crises.")
        else:
            try:
                paciente = validar_paciente(
                    Paciente(
                        nome,
                        idade,
                        peso,
                        altura,
                        sexo,
                        subtipo,
                        versao_cid,
                        codigo_cid,
                        descricao_cid,
                    )
                )
                d = validar_historico(exames_editados)
                r = validar_referencias(referencias, basal_ok)
                comp = comparar(d, r, basal_ok)
                atributos = atributos_temporais(d)
                atributos.update(contexto_numerico(paciente, hidroxiureia))
                atributos["crises_365d"] = contagem_confirmada(
                    crises, d.data_coleta.max(), cobertura
                )
                st.session_state["resultado" + chave] = {
                    "paciente": paciente,
                    "exames": d,
                    "comparacao": comp,
                    "referencias": r,
                    "crises": crises.copy(),
                    "atributos": atributos,
                    "contexto": contexto,
                    "proveniencia": proveniencia,
                    "alertas": alertas,
                    "hidroxiureia": hidroxiureia,
                }
                st.success("Análise pronta. Abra a aba Análise e relatório.")
            except (ValueError, TypeError) as erro:
                st.error(str(erro))
with abas[4]:
    resultado = st.session_state.get("resultado" + chave)
    if not resultado:
        st.info(
            "Confira os dados na aba Exames e documentos e clique em Analisar dados conferidos."
        )
    else:
        st.caption(
            "Este resultado usa o retrato conferido no último clique em Analisar. Após alterar cadastro, crises ou exames, analise novamente para atualizar o resultado e o PDF."
        )
        d = resultado["exames"]
        comp = resultado["comparacao"]
        st.subheader("Comparação das últimas coletas")
        st.dataframe(
            comp[
                [
                    "nome",
                    "unidade",
                    *(["antigo"] if len(d) >= 3 else []),
                    "anterior",
                    "atual",
                    "diferenca",
                    "variacao_percentual",
                    "faixa_laboratorio",
                ]
            ],
            hide_index=True,
        )
        st.caption(
            f"A comparação acima usa as {min(3, len(d))} últimas coletas. "
            "Os gráficos mostram todo o histórico disponível até a última coleta. "
            "Campos vazios indicam resultados ausentes; não são substituídos por zero."
        )
        for parametro, (rotulo, unidade) in PARAMETROS.items():
            if not d[parametro].notna().any():
                continue
            with st.expander(rotulo, expanded=parametro == "hemoglobina"):
                figura = go.Figure(
                    go.Scatter(
                        x=d.data_coleta,
                        y=d[parametro],
                        mode="lines+markers",
                        connectgaps=False,
                    )
                )
                figura.update_layout(
                    yaxis_title=f"{rotulo} ({unidade})",
                    xaxis_title="Data da coleta",
                    height=300,
                )
                st.plotly_chart(
                    figura, key="grafico" + parametro + chave, width="stretch"
                )
                st.write(comp.set_index("parametro").loc[parametro, "explicacao"])
        presentes = int(d[list(PARAMETROS)].notna().sum().sum())
        st.write(
            f"Qualidade: {presentes} de {len(d) * len(PARAMETROS)} resultados possíveis preenchidos; {len(d)} coletas."
        )
        st.subheader("Estimativa de risco")
        st.info(
            "Estimativa indisponível: esta instalação ainda não possui um modelo "
            "de predição preparado para uso no atendimento. Os gráficos e o "
            "relatório apresentam a evolução dos dados informados. "
            "Isso não significa ausência de risco."
        )
        comentarios = st.text_area(
            "Comentários do médico sobre a evolução e, se disponível, a estimativa",
            key="comentarios" + chave,
        )
        conduta = st.text_area(
            "Conduta e orientações definidas pelo médico", key="conduta" + chave
        )
        incluir_nome = st.checkbox(
            "Incluir o nome informado no PDF confidencial",
            value=True,
            key="nome_pdf" + chave,
        )
        origem_documental = resultado.get("proveniencia") or {}
        sintese = origem_documental.get("sintese", "")
        sintese += "\n" + "\n".join(origem_documental.get("origem", []))
        assinatura = hashlib.sha256(
            (repr(resultado) + comentarios + conduta + str(incluir_nome)).encode()
        ).hexdigest()
        if st.button("Preparar relatório PDF com gráficos", key="preparar" + chave):
            with st.spinner("Gerando PDF localmente..."):
                pdf = relatorio_pdf(
                    resultado["paciente"],
                    d,
                    comp,
                    resultado["referencias"],
                    resultado["crises"],
                    comentarios,
                    conduta,
                    incluir_nome,
                    resultado.get("risco"),
                    resultado.get("explicacoes"),
                    sintese,
                    resultado["contexto"]
                    + " | Hidroxiureia: "
                    + resultado["hidroxiureia"],
                    alertas=resultado["alertas"],
                )
            st.session_state["pdf" + chave] = (assinatura, pdf)
        arquivo_pdf = st.session_state.get("pdf" + chave)
        if arquivo_pdf and arquivo_pdf[0] == assinatura:
            st.download_button(
                "Baixar relatório em PDF",
                arquivo_pdf[1],
                "relatorio_acompanhamento.pdf",
                "application/pdf",
                key="baixar" + chave,
            )
        elif arquivo_pdf:
            st.info("Os comentários ou resultados mudaram. Prepare o PDF novamente.")
