"""Área opcional de experimentos; dados e modelos permanecem na sessão."""

from io import BytesIO
import json
import pandas as pd
import streamlit as st
from .modelos import (
    CLINICAS,
    METADADOS,
    PONTUAIS,
    TEMPORAIS,
    prever,
    treinar,
)


def painel_treinamento(chave):
    st.subheader("Pesquisa e treinamento local")
    st.write(
        "Não acompanha um modelo pré-treinado. Use uma coorte preparada e revisada para pesquisa. Não use nomes, CPF ou dados de demonstração como evidência clínica."
    )
    modelo_csv = pd.DataFrame(columns=METADADOS + CLINICAS + PONTUAIS + TEMPORAIS)
    st.download_button(
        "Baixar estrutura da tabela de treinamento",
        modelo_csv.to_csv(index=False).encode(),
        "estrutura_treinamento.csv",
        "text/csv",
    )
    st.caption(
        "A preparação da coorte e dos rótulos é documentada em docs/PESQUISA.md. A aplicação não deduz eventos futuros de relatórios nem transforma ausência de registro em ausência de crise."
    )
    arquivo = st.file_uploader(
        "Coorte de pesquisa em CSV UTF-8, separado por vírgulas",
        type=["csv"],
        key="coorte" + chave,
    )
    corte = st.text_input("Corte temporal opcional (AAAA-MM-DD)", key="corte" + chave)
    seed = st.number_input(
        "Seed do experimento",
        min_value=0,
        max_value=100000,
        value=42,
        key="seed" + chave,
    )
    revisado = st.checkbox(
        "Revisei os rótulos e a disponibilidade das features até T0; os dados têm uso autorizado para esta pesquisa",
        key="autoria" + chave,
    )
    if st.button("Treinar e comparar modelos", key="treinar" + chave):
        if not arquivo or not revisado:
            st.error("Forneça a coorte e confirme sua revisão.")
        elif arquivo.size > 10_000_000:
            st.error("O CSV excede 10 MB.")
        else:
            try:
                dados = pd.read_csv(BytesIO(arquivo.getvalue()))
                with st.spinner("Treinando no computador..."):
                    resultado = treinar(dados, int(seed), corte_temporal=corte or None)
                resultado["ids_treinamento"] = set(dados.paciente_id.astype(str))
                st.session_state["pesquisa" + chave] = resultado
                anterior = st.session_state.get("resultado" + chave, {})
                for campo in ("risco", "explicacoes", "modelo_ativo", "x", "faltantes"):
                    anterior.pop(campo, None)
            except ImportError:
                st.error(
                    "Instale requirements-pesquisa.txt para habilitar treinamento."
                )
            except (ValueError, TypeError, KeyError) as erro:
                st.error(str(erro))
    resultado = st.session_state.get("pesquisa" + chave)
    if resultado:
        colunas = [
            "modelo",
            "roc_auc",
            "average_precision",
            "recall_sensibilidade",
            "especificidade",
            "brier",
        ]
        st.dataframe(pd.DataFrame(resultado["resultados"])[colunas], hide_index=True)
        st.warning(
            "Comparação exploratória em um teste interno. Escolher o melhor neste teste exige nova avaliação independente. As probabilidades não recebem recalibração adicional."
        )
        st.download_button(
            "Baixar auditoria do experimento",
            json.dumps(resultado["auditoria"], ensure_ascii=False, indent=2).encode(),
            "auditoria_experimento.json",
            "application/json",
        )
    return resultado


def painel_predicao(chave, atributos, t0, resultado):
    experimento = st.session_state.get("pesquisa" + chave)
    st.subheader("Análise preditiva e explicável")
    if not experimento:
        st.info(
            "Probabilidade não calculada: nenhum modelo treinado está ativo. Isso não significa risco zero. A comparação dos exames e o PDF descritivo estão disponíveis."
        )
        return
    nome = st.selectbox(
        "Modelo experimental", list(experimento["modelos"]), key="modelo" + chave
    )
    id_atual = st.text_input(
        "Identificador pseudônimo do paciente avaliado (nunca o nome)",
        key="id_pred" + chave,
    )
    compativel = st.checkbox(
        "Conferi que a população, as unidades e as features são compatíveis com a coorte; este paciente não integra a coorte usada no experimento",
        key="compat" + chave,
    )
    if st.button("Calcular estimativa experimental", key="prever" + chave):
        if not compativel or not id_atual.strip():
            st.error("Informe um identificador pseudônimo e confira a compatibilidade.")
        elif id_atual in experimento["ids_treinamento"]:
            st.error(
                "Este identificador pertence à coorte do experimento; não pode ser apresentado como caso independente."
            )
        else:
            try:
                modelo = experimento["modelos"][nome]
                p, x, faltantes = prever(modelo, atributos)
                resultado["risco"] = {
                    "probabilidade": p,
                    "horizonte": modelo["horizonte"],
                    "t0": str(t0.date()),
                    "modelo": nome,
                    "metricas": modelo["metricas"],
                }
                resultado["modelo_ativo"] = modelo
                resultado["x"] = x
                resultado["faltantes"] = faltantes
                resultado.pop("explicacoes", None)
            except ValueError as erro:
                st.error(str(erro))
    if "risco" not in resultado:
        return
    risco = resultado["risco"]
    st.metric(
        "Estimativa experimental, sem recalibração",
        f"{100 * risco['probabilidade']:.1f}%",
    )
    st.write(
        f"Horizonte: {risco['horizonte']} dias após {risco['t0']}. Modelo: {risco['modelo']}."
    )
    st.caption(
        "Não confirma ocorrência de crise e não determina conduta. O subtipo consta do contexto, mas esta primeira infraestrutura numérica ainda não o utiliza como feature."
    )
    if resultado["faltantes"]:
        st.warning(
            "Features imputadas pela mediana do treino: "
            + ", ".join(resultado["faltantes"])
        )
    if st.button("Gerar SHAP e LIME", key="explicar" + chave):
        try:
            from .explicacoes import explicar

            with st.spinner("Calculando explicações locais..."):
                resultado["explicacoes"] = explicar(
                    resultado["modelo_ativo"], resultado["x"]
                )
        except ImportError:
            st.error("Instale requirements-pesquisa.txt, incluindo SHAP e LIME.")
        except (ValueError, TypeError, RuntimeError) as erro:
            st.error("Explicações indisponíveis: " + str(erro))
    if "explicacoes" in resultado:
        explicacoes = resultado["explicacoes"]
        for metodo in ("shap", "lime"):
            st.markdown("**" + metodo.upper() + "**")
            st.dataframe(pd.DataFrame(explicacoes[metodo]).head(10), hide_index=True)
        st.write(explicacoes["comparacao"])
        st.caption(
            "SHAP: contribuição na escala da probabilidade. LIME: coeficiente local com padronização; escalas não são diretamente comparáveis. Concordância não prova correção clínica ou causalidade. Variáveis ausentes explicam valores imputados."
        )
