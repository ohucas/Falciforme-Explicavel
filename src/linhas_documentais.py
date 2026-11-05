import re

UNIDADE = (
    r"g/d[lL]|f[lL]|p[gG]|%|" r"(?:milh[oõ]es|mil|c[eé]lulas)/(?:µ[lL]|u[lL]|mm[³3])"
)


def linhas_de_resultados(texto, aliases):
    """Une apenas rótulo isolado, valor isolado e unidade explícita adjacente."""
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    resultado = []
    for indice, linha in enumerate(linhas):
        rotulo = any(
            re.fullmatch(rf"(?:{alias})\s*[:=]?", linha, flags=re.I)
            for alias in aliases.values()
        )
        if not rotulo:
            resultado.append(linha)
            continue
        proxima = indice + 1
        while proxima < len(linhas) and linhas[proxima] in {
            "X",
            "x",
            "↑",
            "↓",
            "*",
            "✓",
            "✗",
            "❎",
            "❌",
        }:
            proxima += 1
        if proxima >= len(linhas):
            resultado.append(linha)
            continue
        valor = linhas[proxima]
        if not re.fullmatch(rf"\d+(?:[.,]\d+)*(?:\s*(?:{UNIDADE}))?", valor):
            resultado.append(linha)
            continue
        unidade = ""
        if proxima + 1 < len(linhas) and re.fullmatch(
            UNIDADE, linhas[proxima + 1], flags=re.I
        ):
            unidade = " " + linhas[proxima + 1]
        resultado.append(linha + " " + valor + unidade)
    return resultado
