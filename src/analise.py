"""Núcleo determinístico e auditável, sem LLM, treinamento ou rede."""

from datetime import date
import math
import re
import pandas as pd

PARAMETROS = {
    "hemoglobina": ("Hemoglobina", "g/dL"),
    "hematocrito": ("Hematócrito", "%"),
    "hemacias": ("Hemácias", "milhões/µL"),
    "vcm": ("VCM", "fL"),
    "hcm": ("HCM", "pg"),
    "chcm": ("CHCM", "g/dL"),
    "rdw": ("RDW-CV", "%"),
    "leucocitos": ("Leucócitos", "células/µL"),
    "plaquetas": ("Plaquetas", "mil/µL"),
}
SUBTIPOS = [
    "HbSS",
    "HbSC",
    "HbS/β⁰-talassemia",
    "HbS/β⁺-talassemia",
    "Outro / não informado",
]
FONTES = {
    "F1": ("CDC — Febre", "https://www.cdc.gov/sickle-cell/complications/fever.html"),
    "F2": (
        "NHLBI — Sintomas",
        "https://www.nhlbi.nih.gov/health/sickle-cell-disease/symptoms",
    ),
    "F3": (
        "NHLBI — Acompanhamento",
        "https://www.nhlbi.nih.gov/health/sickle-cell-disease/living-with",
    ),
    "F4": (
        "GeneReviews — Doença falciforme",
        "https://www.ncbi.nlm.nih.gov/books/NBK1377/",
    ),
}
AVISO = (
    "Protótipo educativo e descritivo. Não confirma diagnóstico, melhora/piora clínica, infecção ou crise; "
    "não estima probabilidades nem altera tratamentos. Solicite revisão dos exames pela equipe de saúde. "
    "Resultados habituais não garantem segurança. Sintomas atuais prevalecem sobre exames antigos."
)


def vazio():
    return pd.DataFrame(
        {
            "data_coleta": ["", "", ""],
            **{p: [float("nan")] * 3 for p in PARAMETROS},
            "peso_kg": [float("nan")] * 3,
        }
    )


def validar_exames(df, hoje=None, min_coletas=3, max_coletas=3):
    """Contrato estrito: 3 datas ISO distintas; colunas numéricas em unidades fixadas."""
    d = df.copy().reset_index(drop=True)
    hoje = hoje or date.today()
    if not min_coletas <= len(d) <= max_coletas:
        raise ValueError(
            f"Informe entre {min_coletas} e {max_coletas} coletas, sem duplicar exames."
        )
    exigidas = {"data_coleta", *PARAMETROS}
    faltam = exigidas - set(d.columns)
    if faltam:
        raise ValueError("Colunas ausentes: " + ", ".join(sorted(faltam)))
    extras = set(d.columns) - exigidas - {"peso_kg"}
    if extras:
        raise ValueError(
            "Colunas não previstas: "
            + ", ".join(sorted(extras))
            + ". Use o modelo sem identificadores pessoais."
        )
    datas = []
    for value in d["data_coleta"]:
        s = (
            value.date().isoformat()
            if isinstance(value, pd.Timestamp)
            else str(value).strip()
        )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            raise ValueError("Use datas reais no formato AAAA-MM-DD.")
        try:
            dt = date.fromisoformat(s)
        except ValueError:
            raise ValueError("Data de coleta inválida.") from None
        if dt > hoje:
            raise ValueError("Uma coleta não pode ter data futura.")
        datas.append(dt)
    if len(set(datas)) != len(datas):
        raise ValueError("As datas de coleta devem ser diferentes.")
    d["data_coleta"] = pd.to_datetime(datas)
    for p in [*PARAMETROS, "peso_kg"]:
        if p not in d:
            d[p] = float("nan")
        try:
            d[p] = pd.to_numeric(d[p], errors="raise")
        except (ValueError, TypeError):
            raise ValueError(
                f"{p}: informe somente números, sem unidades na célula."
            ) from None
        for val in d[p].dropna():
            if not math.isfinite(float(val)) or val <= 0:
                raise ValueError(
                    f"{p}: valor deve ser positivo e finito, ou ficar ausente."
                )
    if any(d.loc[i, list(PARAMETROS)].isna().all() for i in d.index):
        raise ValueError("Cada coleta precisa de pelo menos um resultado laboratorial.")
    return d.sort_values("data_coleta").reset_index(drop=True)


def numero(v):
    return None if pd.isna(v) else float(v)


def referencias_vazias():
    return pd.DataFrame(
        [
            {
                "parametro": p,
                "min_laboratorio": float("nan"),
                "max_laboratorio": float("nan"),
                "basal_individual": float("nan"),
            }
            for p in PARAMETROS
        ]
    )


def validar_referencias(refs, basal_confirmado=False):
    d = refs.copy()
    colunas = {"parametro", "min_laboratorio", "max_laboratorio", "basal_individual"}
    if set(d.columns) != colunas:
        raise ValueError("Tabela de referências fora do formato esperado.")
    if (
        len(d) != len(PARAMETROS)
        or set(d.parametro) != set(PARAMETROS)
        or d.parametro.duplicated().any()
    ):
        raise ValueError("Cada parâmetro deve aparecer uma vez nas referências.")
    for c in colunas - {"parametro"}:
        try:
            d[c] = pd.to_numeric(d[c], errors="raise")
        except (ValueError, TypeError):
            raise ValueError("Referências devem ser numéricas.") from None
        if any(not math.isfinite(float(v)) or v < 0 for v in d[c].dropna()):
            raise ValueError("Referências devem ser finitas e não negativas.")
    for _, r in d.iterrows():
        lo, hi, base = map(
            numero, [r.min_laboratorio, r.max_laboratorio, r.basal_individual]
        )
        if (lo is None) != (hi is None):
            raise ValueError(
                "Preencha os dois limites do laboratório ou deixe ambos vazios."
            )
        if lo is not None and lo >= hi:
            raise ValueError("O limite inferior deve ser menor que o superior.")
        if base is not None and (base <= 0 or not basal_confirmado):
            raise ValueError(
                "Valor basal exige confirmação de revisão pela equipe de saúde."
            )
    return d


def comparar(exames, refs=None, basal_confirmado=False):
    d = validar_exames(exames, min_coletas=2, max_coletas=500)
    r = validar_referencias(
        refs if refs is not None else referencias_vazias(), basal_confirmado
    ).set_index("parametro")
    result = []
    for p, (nome, unidade) in PARAMETROS.items():
        ultimos = [None] * max(0, 3 - len(d)) + d[p].tail(3).tolist()
        a, b, c = map(numero, ultimos)
        delta = None if b is None or c is None else c - b
        media = None if a is None or b is None else (a + b) / 2
        minimo = None if media is None else min(a, b)
        maximo = None if media is None else max(a, b)
        tendencia = "Dados insuficientes para comparar os três exames"
        if None not in (a, b, c):
            if a == b == c:
                tendencia = "Mesmo valor nas três coletas"
            elif a <= b <= c:
                tendencia = "Sequência não decrescente"
            elif a >= b >= c:
                tendencia = "Sequência não crescente"
            else:
                tendencia = "Variação sem direção única"
        lo, hi, base = map(
            numero,
            [
                r.loc[p, "min_laboratorio"],
                r.loc[p, "max_laboratorio"],
                r.loc[p, "basal_individual"],
            ],
        )
        status = "Não informado"
        if c is not None and lo is not None:
            status = (
                "Abaixo da faixa informada"
                if c < lo
                else (
                    "Acima da faixa informada"
                    if c > hi
                    else "Dentro da faixa informada"
                )
            )
        text = f"{nome}: {tendencia.lower()}."
        if delta is not None:
            text += f" Variação entre as duas últimas coletas: {delta:+.2f} {unidade}."
        if media is not None:
            text += f" Média descritiva dos dois anteriores: {media:.2f} {unidade}; não constitui padrão basal."
        if base is not None and c is not None:
            text += f" Diferença para o basal informado como revisado: {c-base:+.2f} {unidade}."
        text += " A direção numérica não determina melhora ou piora clínica."
        result.append(
            dict(
                parametro=p,
                nome=nome,
                unidade=unidade,
                antigo=a,
                anterior=b,
                atual=c,
                diferenca=delta,
                variacao_percentual=None if delta is None else 100 * delta / b,
                media_dois_anteriores=media,
                min_dois_anteriores=minimo,
                max_dois_anteriores=maximo,
                basal_individual=base,
                diferenca_basal=None if base is None or c is None else c - base,
                faixa_laboratorio=status,
                explicacao=text,
                regra="D01 / D02 / D03",
            )
        )
    return pd.DataFrame(result)


def sinais_alerta(temperatura=None, sinais=()):
    mensagens = []
    if temperatura is not None:
        if not math.isfinite(float(temperatura)) or not 30 <= temperatura <= 45:
            raise ValueError(
                "Confira a temperatura em °C; formato ou valor não suportado."
            )
        if temperatura >= 38.5:
            mensagens.append(
                (
                    "S01",
                    "Febre de 38,5 °C ou mais: procure atendimento de urgência agora; não aguarde a análise dos exames.",
                    "F1",
                )
            )
    if sinais:
        mensagens.append(
            (
                "S02",
                "Sinal de alerta informado: procure atendimento de urgência agora. A ausência de alterações em exames antigos não exclui uma urgência.",
                "F2",
            )
        )
    return mensagens


def relatorio_texto(contexto, exames, comparacao, alertas, observacoes):
    d = validar_exames(exames)
    lines = [
        "ACOMPANHAMENTO LABORATORIAL — PROTÓTIPO 0.2",
        AVISO,
        "",
        f"Subtipo informado: {contexto['subtipo']}",
        f"Idade atual informada: {contexto.get('idade','Não informada')}",
        "Idade e peso são contexto; não há correção automática de valores por essas variáveis.",
        "Faixas laboratoriais foram transcritas pelo usuário, sem validação automática da adequação por idade/sexo/gestação.",
        "Intervalos de coleta: "
        + str((d.data_coleta.iloc[1] - d.data_coleta.iloc[0]).days)
        + " e "
        + str((d.data_coleta.iloc[2] - d.data_coleta.iloc[1]).days)
        + " dias.",
        "Dias desde a coleta mais recente: "
        + str((pd.Timestamp(date.today()) - d.data_coleta.iloc[-1]).days),
        "",
        "ALERTAS DE SINTOMAS",
    ]
    lines.extend(f"{r}: {m} ({fonte})" for r, m, fonte in alertas)
    if not alertas:
        lines.append(
            "Nenhum alerta foi acionado pelas respostas fornecidas. Isso NÃO significa ausência de risco ou liberação médica."
        )
    lines += [
        "",
        "CONTEXTO E LIMITES",
        *observacoes,
        "",
        "RESULTADOS CONFERIDOS",
        d.to_string(index=False),
        "",
        "COMPARAÇÕES",
    ]
    for _, r in comparacao.iterrows():
        lines.extend(
            [
                r.explicacao,
                "Faixa do laudo: " + r.faixa_laboratorio + "; regra: " + r.regra,
                "",
            ]
        )
    lines += [
        "AUTOCUIDADO EDUCATIVO — F3",
        "Mantenha o acompanhamento e siga o plano prescrito; não altere medicamentos com base no relatório.",
        "Converse com sua equipe sobre hidratação adequada às suas condições e sobre vacinação.",
        "Evite situações que sua equipe identificou como desencadeantes e siga seu plano de ação para dor.",
        "Pergunte à equipe como interpretar as mudanças e se os exames precisam ser repetidos.",
        "",
        "FONTES E RASTREABILIDADE",
    ]
    lines.extend(f"{k}: {t} — {url}" for k, (t, url) in FONTES.items())
    lines += [
        "D01: diferença atual menos anterior; percentual usa o anterior como denominador.",
        "D02: média e intervalo observado dos dois anteriores; não estimam faixa normal.",
        "D03: comparação numérica com faixa do laudo e basal informado; não diagnostica.",
        "S01/S02: mensagens de segurança baseadas nas fontes indicadas, não previsões de eventos.",
        "",
        "Conteúdo educativo baseado em fontes públicas, ainda sem validação clínica deste software.",
    ]
    return "\n".join(lines)
