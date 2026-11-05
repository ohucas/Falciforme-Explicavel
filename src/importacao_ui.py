from datetime import date
import hashlib
import math
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
from .preenchimento import sugerir_preenchimento
from .analise import PARAMETROS, vazio


def tabela_sem_coletas():
    return vazio().iloc[:0].copy()


def entrada_documentos(k):
    st.info(
        "Leitura local de PDF, DOCX, TXT e imagens. PDFs digitalizados e fotos usam OCR quando instalado. Confira valores e datas antes de analisar. Relatórios narrativos podem gerar síntese documental."
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
                (
                    Path(__file__).resolve().parents[1]
                    / "exemplos"
                    / "relatorio_ficticio.txt"
                ).read_bytes(),
            )
        ]
    else:
        up = st.file_uploader(
            "Envie até dez documentos da mesma pessoa",
            type=["pdf", "docx", "txt", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="docs_upload" + k,
        )
        if len(up) > 10:
            st.error("Limite de dez documentos por sessão de importação.")
            return tabela_sem_coletas(), None
        for f in up:
            if f.size > 5_000_000:
                st.error("Um documento excede 5 MB.")
                return tabela_sem_coletas(), None
            arquivos.append((f.name, f.getvalue()))
    docs = []
    for i, (nome, conteudo) in enumerate(arquivos, 1):
        try:
            doc = ler_documento(conteudo, nome, f"Documento {i}")
        except ValueError as err:
            st.error(f"Documento {i}: {err}")
            continue
        docs.append(doc)
    automatico = st.checkbox(
        "Preencher automaticamente resultados e datas reconhecidos para revisão",
        value=True,
        key="preenchimento_automatico" + k,
    )
    st.caption(
        "O preenchimento usa os padrões suportados. Datas ambíguas, valores não "
        "reconhecidos e unidades incompatíveis exigem correção. A confirmação "
        "documental e a conferência médica continuam obrigatórias."
    )
    tabelas = []
    st.caption(
        "Fluxo: enviar documentos, marcar resultados em usar, conferir datas e unidades, confirmar a revisão e analisar."
    )
    registros = []
    for doc in docs:
        token = k + doc["id"] + doc["sha256"][:12]
        with st.expander(doc["id"] + " — texto e trechos para revisão", expanded=True):
            for aviso in doc["avisos"]:
                st.warning(aviso)
            texto = "\n\n".join(
                f"[Página/bloco {p['pagina']}]\n{p['texto']}" for p in doc["paginas"]
            )
            st.caption(
                "Texto extraído para conferência. Use o botão de copiar do bloco "
                "ou baixe o TXT. Ele pode conter dados pessoais; remova-os antes "
                "de compartilhar. Este texto não entra integralmente no PDF."
            )
            st.code(texto, language="text", wrap_lines=True, height=220)
            st.download_button(
                "Baixar texto extraído (.txt)",
                data=texto.encode("utf-8"),
                file_name=f"texto_extraido_{doc['id'].replace(' ', '_')}.txt",
                mime="text/plain; charset=utf-8",
                key="baixar_texto" + token,
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
                    return tabela_sem_coletas(), None
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
            if automatico:
                cand = sugerir_preenchimento(doc, cand)
            if cand.empty:
                st.caption(
                    "Não foram localizados resultados numéricos pelos padrões suportados. Isso não significa ausência de achados no relatório."
                )
            else:
                mesma_coleta = st.checkbox(
                    "Todos os resultados numéricos deste documento são da mesma coleta",
                    key="mesma_coleta" + token,
                )
                if mesma_coleta:
                    coleta = st.date_input(
                        "Data da coleta conferida no documento",
                        value=None,
                        max_value=date.today(),
                        format="DD/MM/YYYY",
                        key="coleta_documento" + token,
                    )
                    if coleta is not None:
                        cand["data_coleta"] = coleta.isoformat()
                        cand["origem_data"] = "informada na revisão"
                        if automatico:
                            # Reavalia seleção após a data explicitamente informada.
                            for linha_indice, linha in cand.iterrows():
                                valor = linha["valor_confirmado"]
                                cand.at[linha_indice, "usar"] = (
                                    pd.notna(valor)
                                    and math.isfinite(float(valor))
                                    and float(valor) > 0
                                    and linha["unidade_confirmada"]
                                    == PARAMETROS[linha["parametro"]][1]
                                )
                    st.caption(
                        "Essa data será aplicada a todos os candidatos deste documento. Não use esta opção se ele citar várias coletas."
                    )
                tabelas.append(cand)
    if not docs:
        st.caption("Selecione um documento ou a demonstração fictícia.")
        return tabela_sem_coletas(), None
    versao_documentos = hashlib.sha256(
        "".join(d["sha256"] for d in docs).encode()
    ).hexdigest()[:12]
    documental_ok = st.checkbox(
        "Conferi os trechos selecionados, a temporalidade e que todos os documentos pertencem à mesma pessoa",
        key="documental_ok" + k + versao_documentos,
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
            "O leitor não reconheceu resultados numéricos nos padrões suportados. A saída disponível é documental. Não criaremos gráficos ou valores ausentes. Você também pode transcrever resultados conhecidos na tabela abaixo."
        )
        return tabela_sem_coletas(), (
            {
                "sintese": sintese_documental(registros),
                "origem": [],
                "confirmado": documental_ok,
            }
            if documental_ok
            else None
        )
    st.markdown("**Resultados reconhecidos — confira os campos preenchidos**")
    st.caption(
        "Com preenchimento automático ativo, candidatos com valor, unidade compatível e data de coleta identificada começam selecionados. Confira cada associação. Complete os demais resultados e suas datas de COLETA, quando conhecidos. Valores podem se referir a momentos distintos; revise o trecho. Não faça conversões sem confirmação."
    )
    base_candidatos = pd.concat(tabelas, ignore_index=True)
    versao_candidatos = hashlib.sha256(
        base_candidatos.to_json(date_format="iso").encode()
    ).hexdigest()[:12]
    edited = st.data_editor(
        base_candidatos,
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
            "origem_data",
            "data_contexto",
        ],
        key="candidatos" + k + versao_candidatos,
        column_config={
            "usar": st.column_config.CheckboxColumn("Usar resultado", default=False),
            "data_coleta": st.column_config.TextColumn(
                "Data da coleta (DD/MM/AAAA ou AAAA-MM-DD)"
            ),
        },
        width="stretch",
    )
    if "origem_data" in edited.columns:
        diferentes = edited["data_coleta"].ne(base_candidatos["data_coleta"])
        edited.loc[diferentes, "origem_data"] = "informada na revisão"
    origens = edited.get("origem_data", pd.Series("", index=edited.index))
    datas_atendimento = edited["usar"].eq(True) & origens.eq(
        "atendimento — confirmar coleta"
    )
    datas_ok = True
    if datas_atendimento.any():
        st.warning(
            "O laudo informa data de atendimento, sem data de coleta explícita para "
            "estes resultados. A tabela recebeu essa data como SUGESTÃO. "
            "Confirme que ela corresponde à coleta ou corrija a data na tabela de resultados reconhecidos."
        )
        datas_ok = st.checkbox(
            "Confirmei que as datas sugeridas pelo atendimento correspondem às coletas",
            key="datas_atendimento" + k + versao_candidatos,
        )
    resumo = []
    documentos_pendentes = []
    for doc in docs:
        linhas = edited[edited["documento"].eq(doc["id"])]
        escolhidos = linhas[linhas["usar"].eq(True)]
        datas_validas = sorted(
            {str(v) for v in escolhidos["data_coleta"] if str(v).strip()}
        )
        status = "Pronto para conferência"
        if linhas.empty:
            status = "Nenhum resultado reconhecido; transcreva os valores do laudo"
        elif escolhidos.empty:
            status = "Sem resultados selecionados; confira data, unidade e coluna Usar"
        elif escolhidos["data_coleta"].fillna("").astype(str).str.strip().eq("").any():
            status = "Data de coleta pendente"
        if status != "Pronto para conferência":
            documentos_pendentes.append(doc["id"])
        resumo.append(
            {
                "Documento": doc["id"],
                "Reconhecidos": len(linhas),
                "Selecionados": len(escolhidos),
                "Datas selecionadas": ", ".join(datas_validas) or "Não identificada",
                "Situação": status,
            }
        )
    st.markdown("**Conferência da importação por documento**")
    st.dataframe(pd.DataFrame(resumo), hide_index=True, width="stretch")
    importacao_ok = True
    if documentos_pendentes:
        st.warning(
            "Há documentos sem resultados prontos para análise: "
            + ", ".join(documentos_pendentes)
            + ". Eles não entrarão automaticamente na comparação. Confira os respectivos trechos e campos."
        )
        importacao_ok = st.checkbox(
            "Continuar apenas com os resultados disponíveis, ciente dos documentos pendentes",
            key="aceitar_importacao_parcial" + k + versao_candidatos,
        )
    selecionados = int(edited["usar"].eq(True).sum())
    st.caption(f"Resultados selecionados: {selecionados} de {len(edited)}.")
    if not documental_ok:
        st.info(
            "A tabela abaixo já mostra os resultados reconhecidos. A análise "
            "permanece bloqueada até você confirmar a conferência documental."
        )
    try:
        tabela = montar_tabela(edited)
    except ValueError as err:
        st.error(str(err))
        return tabela_sem_coletas(), None
    if tabela.empty:
        st.info(
            "Nenhum resultado selecionado em usar. O documento pode gerar síntese, mas ainda não há coletas para comparar."
        )
        return tabela_sem_coletas(), {
            "sintese": sintese_documental(registros),
            "origem": [],
            "confirmado": documental_ok,
        }
    st.success(
        f"{len(tabela)} coleta(s) preenchida(s) automaticamente na tabela de exames para revisão."
    )
    if len(tabela) < 2:
        st.info(
            "A comparação exige pelo menos duas datas de coleta distintas. Adicione outro exame ou confira as datas dos resultados selecionados."
        )
    confirmed = edited[edited.usar.eq(True)].copy()
    origem = [
        "Informações numéricas transcritas de relatórios, não verificadas contra laudos originais."
    ]
    for _, r in confirmed.iterrows():
        origem.append(
            f"{r['documento']}, página/bloco {r['pagina']}: {r['parametro']} em {r['data_coleta']}; origem da data: {r.get('origem_data', 'conferida')}; extraído como {r['valor_texto']} {r['unidade_origem']}; valor para revisão: {r['valor_confirmado']} {r['unidade_confirmada']}."
        )
    origem.append(
        "Trechos históricos não são sintomas atuais. Mudanças na tabela final precisam ser conferidas; o rastreio documental descreve a transcrição antes dessas edições."
    )
    st.caption(
        "A tabela abaixo recebe os valores selecionados. Complete apenas dados reais com origem conhecida e confira novamente antes de comparar."
    )
    return tabela, {
        "sintese": sintese_documental(registros),
        "origem": origem,
        "confirmado": documental_ok and datas_ok and importacao_ok,
    }
