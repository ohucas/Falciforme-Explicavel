from calendar import monthrange
from datetime import date
import numpy as np
import pandas as pd
from .analise import PARAMETROS, validar_exames

COLUNAS_CRISES = [
    "ano",
    "mes",
    "dia",
    "tipo",
    "atendimento",
    "fonte",
    "confirmado",
    "observacoes",
]
TIPOS = ["Vaso-oclusiva", "Outra / não determinada"]
ATENDIMENTOS = ["Internação", "Emergência sem internação", "Outro", "Não informado"]


def crises_vazias():
    return pd.DataFrame(
        {
            "ano": pd.Series(dtype="float64"),
            "mes": pd.Series(dtype="float64"),
            "dia": pd.Series(dtype="float64"),
            "tipo": pd.Series(dtype="str"),
            "atendimento": pd.Series(dtype="str"),
            "fonte": pd.Series(dtype="str"),
            "confirmado": pd.Series(dtype="bool"),
            "observacoes": pd.Series(dtype="str"),
        }
    )


def validar_historico(exames):
    return validar_exames(exames, min_coletas=2, max_coletas=500)


def inteiro(valor, campo, opcional=False):
    if pd.isna(valor) or str(valor).strip() == "":
        if opcional:
            return None
        raise ValueError(f"Informe {campo} em cada crise.")
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{campo}: use número inteiro.") from None
    if not np.isfinite(n) or not n.is_integer():
        raise ValueError(f"{campo}: use número inteiro.")
    return int(n)


def validar_crises(tabela, hoje=None):
    hoje = hoje or date.today()
    registros = []
    for _, linha in tabela.iterrows():
        if all(
            pd.isna(linha.get(c)) or str(linha.get(c)).strip() == ""
            for c in ["ano", "mes", "dia"]
        ):
            continue
        ano = inteiro(linha.get("ano"), "ano")
        mes = inteiro(linha.get("mes"), "mês", True)
        dia = inteiro(linha.get("dia"), "dia", True)
        if dia is not None and mes is None:
            raise ValueError("Uma crise com dia precisa de mês.")
        try:
            inicio = date(ano, mes or 1, dia or 1)
            fim = date(ano, mes or 12, dia or monthrange(ano, mes or 12)[1])
        except ValueError:
            raise ValueError("Período inválido no histórico de crises.") from None
        if inicio > hoje:
            raise ValueError("Uma crise passada não pode começar no futuro.")
        fonte = str(linha.get("fonte", "")).strip()
        confirmado = linha.get("confirmado") is True or linha.get("confirmado") == True
        if confirmado and (not fonte or fonte == "nan"):
            raise ValueError(
                "Evento confirmado exige fonte documental ou identificação da avaliação médica."
            )
        registros.append(
            {
                "ano": ano,
                "mes": mes,
                "dia": dia,
                "tipo": linha.get("tipo") or TIPOS[1],
                "atendimento": linha.get("atendimento") or "Não informado",
                "fonte": fonte if fonte != "nan" else "Não informada",
                "confirmado": bool(confirmado),
                "observacoes": str(linha.get("observacoes", "")),
                "inicio": inicio,
                "fim": fim,
                "precisao": "Dia" if dia else "Mês" if mes else "Ano",
            }
        )
    d = pd.DataFrame(registros)
    if not d.empty:
        # Mesmo dia pode ter eventos distintos, mas exige revisão explícita na origem.
        if d[d.precisao.eq("Dia")].duplicated(["inicio", "tipo", "fonte"]).any():
            raise ValueError("Possível crise duplicada: confira data, tipo e fonte.")
        d = d.sort_values("inicio").reset_index(drop=True)
    return d


def resumo_anual(crises):
    if crises.empty:
        return pd.DataFrame(
            columns=["ano", "registradas", "confirmadas", "internacoes"]
        )
    d = crises.assign(internacao=crises.atendimento.eq("Internação").astype(int))
    return d.groupby("ano", as_index=False).agg(
        registradas=("ano", "size"),
        confirmadas=("confirmado", "sum"),
        internacoes=("internacao", "sum"),
    )


def atributos_temporais(exames, t0=None):
    """Usa somente coletas até T0; inclinação em unidades por dia real."""
    d = validar_historico(exames)
    t0 = pd.Timestamp(t0 or d.data_coleta.max()).normalize()
    d = d[d.data_coleta.le(t0)]
    if len(d) < 2:
        raise ValueError("São necessárias duas coletas disponíveis até T0.")
    saida = {}
    for parametro in PARAMETROS:
        serie = d[parametro]
        anterior = serie.iloc[-2]
        atual = serie.iloc[-1]
        validos = d.loc[serie.notna(), ["data_coleta", parametro]]
        diferenca = atual - anterior
        x = (validos.data_coleta - validos.data_coleta.min()).dt.days.to_numpy()
        inclinacao = (
            float(np.polyfit(x, validos[parametro], 1)[0])
            if len(validos) >= 2
            else np.nan
        )
        saida.update(
            {
                f"{parametro}_atual": atual,
                f"{parametro}_anterior": anterior,
                f"{parametro}_delta": diferenca,
                f"{parametro}_media": serie.mean(),
                f"{parametro}_desvio": serie.std(ddof=1),
                f"{parametro}_inclinacao": inclinacao,
            }
        )
    saida["n_coletas"] = len(d)
    saida["dias_ultima_coleta"] = (t0 - d.data_coleta.max()).days
    return saida


def contagem_confirmada(crises, t0, cobertura_completa=False):
    """Ausência de registro não vira zero sem cobertura explicitamente revisada."""
    if not cobertura_completa:
        return np.nan
    t0 = pd.Timestamp(t0).date()
    inicio = t0 - pd.Timedelta(days=365)
    if crises.empty:
        return 0.0
    eventos = crises[
        crises.confirmado
        & crises.tipo.eq("Vaso-oclusiva")
        & crises.fim.le(t0)
        & crises.inicio.gt(inicio)
    ]
    # Um período que atravessa T0 ou o início da janela torna a contagem indeterminada.
    incertos = crises[
        crises.confirmado
        & crises.tipo.eq("Vaso-oclusiva")
        & crises.inicio.le(t0)
        & crises.fim.gt(inicio)
        & (~crises.fim.le(t0) | ~crises.inicio.gt(inicio))
    ]
    return np.nan if len(incertos) else float(len(eventos))


def rotulo_futuro(eventos_dia, t0, fim_acompanhamento, horizonte=30):
    """Somente datas exatas confirmadas; desconhecido permanece None."""
    if horizonte not in (7, 14, 30, 60):
        raise ValueError("Horizonte deve ser 7, 14, 30 ou 60 dias.")
    t0 = pd.Timestamp(t0).normalize()
    fim = t0 + pd.Timedelta(days=horizonte)
    acompanhamento = pd.Timestamp(fim_acompanhamento).normalize()
    datas = pd.to_datetime(eventos_dia)
    if any((datas > t0) & (datas <= min(fim, acompanhamento))):
        return 1
    return 0 if acompanhamento >= fim else None
