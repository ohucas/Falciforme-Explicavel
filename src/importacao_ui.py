"""Conferência de documentos. Conteúdo fica apenas na sessão, sem gravação automática."""

from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st
from .documentos import (
    ler_documento,
    candidatos,
    datas_mencionadas,
    montar_tabela,
    sintese_documental,
)
from .analise import vazio


def entrada_documentos(k):
    st.info(
        "Leitura assistida de PDF com texto, DOCX ou TXT. Relatório narrativo pode gerar uma síntese sem gráficos. Não há OCR ou compreensão clínica livre nesta versão."
    )
    st.caption(
        "Datas de emissão e de coleta são diferentes. Selecionaremos apenas resultados observados, nunca metas, hipóteses ou números de referência. A extração por padrões é limitada e exige revisão."
    )
    exemplo = st.checkbox(
        "Usar relatório fictício para aprender", key="rel_exemplo" + k
    )
    arquivos = []
    if exemplo:
        arquivos = [
            (
                "relatorio_ficticio.txt",
                Path("exemplos/relatorio_ficticio.txt").read_bytes(),
            )
        ]
    else:
        up = st.file_uploader(
            "Envie até dez documentos da mesma pessoa",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="docs_upload" + k,
        )
        if len(up) > 10:
            st.error("Limite de dez documentos por sessão de importação.")
            return vazio(), None
        for f in up:
            if f.size > 5_000_000:
                st.error("Um documento excede 5 MB.")
                return vazio(), None
            arquivos.append((f.name, f.getvalue()))
    docs = []
    for i, (nome, conteudo) in enumerate(arquivos, 1):
        try:
            doc = ler_documento(conteudo, nome, f"Documento {i}")
        except ValueError as err:
            st.error(f"Documento {i}: {err}")
            continue
        docs.append(doc)
    tabelas = []
    registros = []
    for doc in docs:
        token = k + doc["id"] + doc["sha256"][:12]
        with st.expander(doc["id"] + " — texto e trechos para revisão", expanded=True):
            for aviso in doc["avisos"]:
                st.warning(aviso)
            texto = "\n\n".join(
                f"[Página/bloco {p['pagina']}]\n{p['texto']}" for p in doc["paginas"]
            )
            st.text_area(
                "Texto extraído (pode conter identificadores; não será incluído integralmente no relatório)",
                value=texto,
                height=180,
                disabled=True,
                key="texto" + token,
            )
            datas = datas_mencionadas(doc)
            st.caption(
                "Datas encontradas, sem associação automática: "
                + (", ".join(datas) or "nenhuma")
            )
            emissao = st.text_input(
                "Data de emissão do relatório, se conhecida (AAAA-MM-DD)",
                key="emissao" + token,
            )
            trechos = st.text_area(
                "Copie somente os trechos clínicos que deseja levar à síntese. Preserve negações, datas e autoria; remova identificadores.",
                height=100,
                key="trechos" + token,
            )
            if emissao:
                try:
                    dt = date.fromisoformat(emissao)
                    if dt > date.today():
                        raise ValueError()
                except ValueError:
                    st.error("Confira a data de emissão.")
                    return vazio(), None
            registros.append(
                {
                    "id": doc["id"],
                    "data_emissao": emissao,
                    "datas": datas,
                    "trechos": trechos,
                    "avisos": doc["avisos"],
                }
            )
            cand = candidatos(doc)
            if cand.empty:
                st.caption(
                    "Não foram localizados resultados numéricos pelos padrões suportados. Isso não significa ausência de achados no relatório."
                )
            else:
                tabelas.append(cand)
    if not docs:
        st.caption("Selecione um documento ou a demonstração fictícia.")
        return vazio(), None
    documental_ok = st.checkbox(
        "Conferi os trechos selecionados, a temporalidade e que todos os documentos pertencem à mesma pessoa",
        key="documental_ok" + k,
    )
    if documental_ok:
        sintese = sintese_documental(registros)
        from .reports.pdf import documento_pdf

        st.download_button(
            "Baixar síntese documental conferida (.pdf)",
            data=documento_pdf("Síntese documental conferida", sintese),
            file_name="sintese_documental.pdf",
            mime="application/pdf",
            key="download_docs" + k,
        )
    if not tabelas:
        st.info(
            "Sem resultados numéricos confirmados, a saída será documental. Não criaremos gráficos ou valores ausentes. Você também pode transcrever resultados conhecidos na tabela abaixo."
        )
        return vazio(), (
            {"sintese": sintese_documental(registros), "origem": []}
            if documental_ok
            else None
        )
    st.markdown("**Resultados candidatos — selecione somente os que conferiu**")
    st.caption(
        "“usar” começa desmarcado. Informe a data da COLETA em cada resultado selecionado e a unidade padrão. Datas mencionadas no texto não são atribuídas automaticamente. Valores podem se referir a momentos distintos; revise o trecho. Não faça conversões sem confirmação."
    )
    edited = st.data_editor(
        pd.concat(tabelas, ignore_index=True),
        num_rows="fixed",
        hide_index=True,
        disabled=[
            "documento",
            "pagina",
            "parametro",
            "valor_texto",
            "unidade_origem",
            "trecho",
            "observacao",
        ],
        key="candidatos" + k + "".join(d["sha256"][:8] for d in docs),
        width="stretch",
    )
    if not documental_ok:
        return vazio(), None
    try:
        tabela = montar_tabela(edited)
    except ValueError as err:
        st.error(str(err))
        return vazio(), None
    if tabela.empty:
        return vazio(), {"sintese": sintese_documental(registros), "origem": []}
    confirmed = edited[edited.usar.eq(True)].copy()
    origem = [
        "Informações numéricas transcritas de relatórios, não verificadas contra laudos originais."
    ]
    for _, r in confirmed.iterrows():
        origem.append(
            f"{r['documento']}, página/bloco {r['pagina']}: {r['parametro']} em {r['data_coleta']}; extraído como {r['valor_texto']} {r['unidade_origem']}; confirmado pelo usuário como {r['valor_confirmado']} {r['unidade_confirmada']}."
        )
    origem.append(
        "Trechos históricos não são sintomas atuais. Mudanças na tabela final precisam ser conferidas; o rastreio documental descreve a transcrição antes dessas edições."
    )
    st.caption(
        "A tabela abaixo recebe os valores selecionados. Complete apenas dados reais com origem conhecida e confira novamente antes de comparar."
    )
    return tabela, {"sintese": sintese_documental(registros), "origem": origem}
