"""Explicadores reais e comparação de rankings; nenhuma justificativa clínica gerada."""

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, rankdata, spearmanr


def comparar_rankings(shap_valores, lime_valores, k=5):
    a = np.asarray(shap_valores, dtype=float)
    b = np.asarray(lime_valores, dtype=float)
    k = min(k, len(a))

    # Inclui empates: não escolhe arbitrariamente um subconjunto de contribuições iguais.
    def topo(v):
        absolutos = np.abs(v)
        limiar = np.sort(absolutos)[-k]
        return set(np.flatnonzero((absolutos >= limiar) & (absolutos > 0)))

    sa, sb = topo(a), topo(b)
    uniao = sa | sb
    ra, rb = rankdata(-np.abs(a)), rankdata(-np.abs(b))
    rho = spearmanr(ra, rb).statistic if np.std(ra) and np.std(rb) else np.nan
    tau = kendalltau(ra, rb).statistic if np.std(ra) and np.std(rb) else np.nan
    return {
        "jaccard_top_k": len(sa & sb) / len(uniao) if uniao else None,
        "spearman": float(rho) if np.isfinite(rho) else None,
        "kendall": float(tau) if np.isfinite(tau) else None,
        "k_solicitado": k,
        "indices_comuns": sorted(sa & sb),
    }


def explicar(modelo, x, seed=42, amostras_shap=128, amostras_lime=1000):
    import shap
    from lime.lime_tabular import LimeTabularExplainer

    colunas = modelo["colunas"]
    pipeline = modelo["pipeline"]
    fundo = modelo["background"]
    entrada = pipeline.named_steps["imputacao"].transform(x)[0]

    def probabilidades(valores):
        return pipeline.predict_proba(pd.DataFrame(valores, columns=colunas))

    # Kernel SHAP explica a probabilidade da classe 1 com link identidade.
    estado = np.random.get_state()
    try:
        np.random.seed(seed)
        explicador = shap.KernelExplainer(lambda v: probabilidades(v)[:, 1], fundo)
        valores = np.asarray(
            explicador.shap_values(
                entrada.reshape(1, -1), nsamples=amostras_shap, silent=True
            )
        ).reshape(-1)
    finally:
        np.random.set_state(estado)
    lime = LimeTabularExplainer(
        fundo,
        feature_names=colunas,
        class_names=["Sem evento", "Evento"],
        mode="classification",
        discretize_continuous=False,
        random_state=seed,
    )
    explicacao = lime.explain_instance(
        entrada,
        probabilidades,
        labels=(1,),
        num_features=len(colunas),
        num_samples=amostras_lime,
    )
    pesos = np.zeros(len(colunas))
    for indice, peso in explicacao.as_map()[1]:
        pesos[indice] = peso

    def lista(v):
        indices = np.argsort(-np.abs(v))
        return [{"variavel": colunas[i], "contribuicao": float(v[i])} for i in indices]

    comparacao = comparar_rankings(valores, pesos)
    comparacao["lime_r2_local"] = float(explicacao.score)
    comparacao["shap_residuo_aditivo"] = float(
        probabilidades(entrada.reshape(1, -1))[0, 1]
        - explicador.expected_value
        - valores.sum()
    )
    comparacao["seed"] = seed
    return {"shap": lista(valores), "lime": lista(pesos), "comparacao": comparacao}


def estabilidade(modelo, x, seeds=(42, 43, 44)):
    """Varia a seed na mesma entrada: mede estocasticidade, não robustez clínica."""
    execucoes = [explicar(modelo, x, seed=s) for s in seeds]
    saida = {}
    for metodo in ("shap", "lime"):
        base = {r["variavel"]: r["contribuicao"] for r in execucoes[0][metodo]}
        comparacoes = []
        for resultado in execucoes[1:]:
            outro = {r["variavel"]: r["contribuicao"] for r in resultado[metodo]}
            comparacoes.append(
                comparar_rankings(list(base.values()), [outro[c] for c in base])
            )
        saida[metodo] = comparacoes
    return saida
