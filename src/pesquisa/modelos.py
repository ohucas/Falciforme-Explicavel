"""Treinamento reproduzível por paciente, com pré-processamento só no treino."""

from datetime import datetime
import platform
import numpy as np
import pandas as pd
from ..analise import PARAMETROS

CLINICAS = ["idade", "peso_kg", "altura_cm", "hidroxiureia", "crises_365d"]
PONTUAIS = [f"{p}_atual" for p in PARAMETROS]
TEMPORAIS = [
    f"{p}_{sufixo}"
    for p in PARAMETROS
    for sufixo in ("anterior", "delta", "media", "desvio", "inclinacao")
] + ["n_coletas", "dias_ultima_coleta"]
GRUPOS = {
    "Clínico": CLINICAS,
    "Clínico e pontual": CLINICAS + PONTUAIS,
    "Clínico e longitudinal": CLINICAS + PONTUAIS + TEMPORAIS,
}
METADADOS = ["paciente_id", "t0", "fim_acompanhamento", "horizonte_dias", "target"]


def validar_dataset(dados):
    d = dados.copy()
    if not set(METADADOS).issubset(d.columns):
        raise ValueError("Colunas necessárias: " + ", ".join(METADADOS))
    extras = set(d.columns) - set(METADADOS + CLINICAS + PONTUAIS + TEMPORAIS)
    if extras:
        raise ValueError("Colunas não permitidas: " + ", ".join(sorted(extras)))
    if d.paciente_id.isna().any() or d.paciente_id.astype(str).str.strip().eq("").any():
        raise ValueError("Use paciente_id pseudônimo preenchido em cada linha.")
    for c in ("t0", "fim_acompanhamento"):
        d[c] = pd.to_datetime(d[c], errors="raise")
    if d.duplicated(["paciente_id", "t0"]).any():
        raise ValueError("Há avaliações duplicadas para o mesmo paciente e T0.")
    d["target"] = pd.to_numeric(d.target, errors="raise")
    if not d.target.isin([0, 1]).all():
        raise ValueError(
            "Target deve ser 0 ou 1 confirmado; exclua rótulos desconhecidos."
        )
    if (
        d.horizonte_dias.nunique() != 1
        or not d.horizonte_dias.isin([7, 14, 30, 60]).all()
    ):
        raise ValueError(
            "Cada experimento usa um único horizonte: 7, 14, 30 ou 60 dias."
        )
    fim = d.t0 + pd.to_timedelta(d.horizonte_dias, unit="D")
    # Contrato conservador: coorte completa no horizonte para todas as linhas.
    if (d.fim_acompanhamento < fim).any():
        raise ValueError("Cada linha precisa de acompanhamento completo no horizonte.")
    for c in set(d.columns) - set(METADADOS):
        d[c] = pd.to_numeric(d[c], errors="raise")
        if np.isinf(d[c]).any():
            raise ValueError("Não são aceitos valores infinitos.")
    return d


def metricas_binarias(y, probabilidades):
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.calibration import calibration_curve

    previsto = np.asarray(probabilidades) >= 0.5
    tn, fp, fn, tp = confusion_matrix(y, previsto, labels=[0, 1]).ravel()
    observado, estimado = calibration_curve(
        y, probabilidades, n_bins=5, strategy="quantile"
    )
    return {
        "accuracy": float(accuracy_score(y, previsto)),
        "precision": float(precision_score(y, previsto, zero_division=0)),
        "recall_sensibilidade": float(recall_score(y, previsto, zero_division=0)),
        "especificidade": float(tn / (tn + fp)),
        "f1": float(f1_score(y, previsto, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, probabilidades)),
        "average_precision": float(average_precision_score(y, probabilidades)),
        "brier": float(brier_score_loss(y, probabilidades)),
        "matriz_tn_fp_fn_tp": [int(tn), int(fp), int(fn), int(tp)],
        "calibracao_observado": observado.tolist(),
        "calibracao_estimado": estimado.tolist(),
        "limiar_experimental": 0.5,
    }


def treinar(dados, seed=42, fracao_teste=0.25, corte_temporal=None):
    """Comparações usam a mesma divisão; teste não seleciona o modelo automaticamente."""
    from sklearn import __version__ as versao_sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.base import clone

    d = validar_dataset(dados)
    if len(d) < 16 or d.paciente_id.nunique() < 8:
        raise ValueError(
            "Mínimo operacional: 16 avaliações e 8 pacientes. Isso não é cálculo amostral ou suficiência clínica."
        )
    if corte_temporal:
        corte = pd.Timestamp(corte_temporal)
        # Remove pacientes observados nos dois períodos e purga janelas do treino.
        grupos_teste = set(d.loc[d.t0.gt(corte), "paciente_id"])
        treino = d.index[
            (d.fim_acompanhamento.le(corte)) & ~d.paciente_id.isin(grupos_teste)
        ]
        teste = d.index[d.t0.gt(corte)]
    else:
        divisor = GroupShuffleSplit(
            n_splits=1, test_size=fracao_teste, random_state=seed
        )
        treino_pos, teste_pos = next(divisor.split(d, d.target, groups=d.paciente_id))
        treino = d.index[treino_pos]
        teste = d.index[teste_pos]
    if not len(treino) or not len(teste):
        raise ValueError("Divisão sem linhas: ajuste a coorte ou o corte temporal.")
    if set(d.loc[treino, "paciente_id"]) & set(d.loc[teste, "paciente_id"]):
        raise ValueError("Vazamento de pacientes detectado.")
    if d.loc[treino, "target"].nunique() < 2 or d.loc[teste, "target"].nunique() < 2:
        raise ValueError(
            "Treino e teste precisam de ambas as classes. A divisão não será repetida até obter métricas favoráveis."
        )
    algoritmos = {
        "Regressão logística": LogisticRegression(max_iter=2000, random_state=seed),
        "Árvore de decisão": DecisionTreeClassifier(
            max_depth=4, min_samples_leaf=3, random_state=seed
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=3,
            random_state=seed,
            n_jobs=1,
        ),
    }
    modelos = {}
    resultados = []
    for grupo, candidatos in GRUPOS.items():
        colunas = [c for c in candidatos if c in d and d.loc[treino, c].notna().any()]
        if not colunas:
            continue
        for nome, algoritmo in algoritmos.items():
            pipeline = Pipeline(
                [
                    (
                        "imputacao",
                        SimpleImputer(strategy="median", keep_empty_features=True),
                    ),
                    ("escala", StandardScaler()),
                    ("modelo", clone(algoritmo)),
                ]
            )
            pipeline.fit(d.loc[treino, colunas], d.loc[treino, "target"])
            probabilidades = pipeline.predict_proba(d.loc[teste, colunas])[:, 1]
            avaliacao = metricas_binarias(d.loc[teste, "target"], probabilidades)
            chave = grupo + " | " + nome
            # Background só do treino, imputado na escala original; nunca inclui nome/ID.
            fundo = pipeline.named_steps["imputacao"].transform(d.loc[treino, colunas])
            modelos[chave] = {
                "pipeline": pipeline,
                "colunas": colunas,
                "background": np.asarray(fundo[:40], dtype=float),
                "horizonte": int(d.horizonte_dias.iloc[0]),
                "metricas": avaliacao,
            }
            resultados.append({"modelo": chave, **avaliacao})
    if not modelos:
        raise ValueError("Não há features numéricas disponíveis no treino.")
    auditoria = {
        "versao_software": "0.3",
        "data_treinamento": datetime.now().astimezone().isoformat(),
        "seed": seed,
        "python": platform.python_version(),
        "sklearn": versao_sklearn,
        "divisao": (
            "paciente e corte temporal purgado"
            if corte_temporal
            else "paciente aleatório"
        ),
        "n_treino": len(treino),
        "n_teste": len(teste),
        "pacientes_treino": int(d.loc[treino, "paciente_id"].nunique()),
        "pacientes_teste": int(d.loc[teste, "paciente_id"].nunique()),
        "horizonte": int(d.horizonte_dias.iloc[0]),
        "features": {k: v["colunas"] for k, v in modelos.items()},
        "parametros": {
            k: {c: str(p) for c, p in v["pipeline"].get_params().items()}
            for k, v in modelos.items()
        },
        "metricas": resultados,
        "limites": "Sem validação externa, tuning ou recalibração. AP é average precision, não integral trapezoidal de PR. Não selecionar e voltar a avaliar no mesmo teste.",
    }
    return {"modelos": modelos, "resultados": resultados, "auditoria": auditoria}


def prever(modelo, atributos):
    x = pd.DataFrame([{c: atributos.get(c, np.nan) for c in modelo["colunas"]}])
    x = x.apply(pd.to_numeric, errors="raise")
    faltantes = x.columns[x.isna().any()].tolist()
    # Mais de 40% ausente é bloqueio operacional configurado, não limiar clínico validado.
    if x.notna().sum(axis=1).iloc[0] / len(x.columns) < 0.6:
        raise ValueError(
            "Dados insuficientes: mais de 40% das features do modelo estão ausentes."
        )
    if np.isinf(x.to_numpy()).any():
        raise ValueError("Features infinitas não são aceitas.")
    probabilidade = float(modelo["pipeline"].predict_proba(x)[0, 1])
    return probabilidade, x, faltantes
