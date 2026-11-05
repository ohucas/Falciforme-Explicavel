import math
import re

from .analise import PARAMETROS
from .datas import normalizar_data_coleta
from .unidades import padronizar_resultado

DATA_COLETA = re.compile(
    r"(?i)\b(?:data\s+(?:da\s+|de\s+)?coleta|coleta)\s*"
    r"(?:realizada\s*)?(?:em\s*|de\s*)?[:\-]?\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})"
)


def datas_explicitas(texto):
    datas = set()
    for texto_data in DATA_COLETA.findall(texto):
        try:
            datas.add(normalizar_data_coleta(texto_data).isoformat())
        except ValueError:
            continue
    return datas


def sugerir_preenchimento(documento, candidatos):
    """Preenche só candidatos com data explícita, valor e unidade compatíveis."""
    resultado = candidatos.copy()
    paginas = {p["pagina"]: p["texto"] for p in documento["paginas"]}
    resultado["origem_data"] = ""
    for indice, linha in resultado.iterrows():
        trecho = str(linha["trecho"])
        datas = datas_explicitas(trecho)
        contexto = linha.get("data_contexto", "")
        if (
            not datas
            and contexto
            and not re.search(
                r"(?i)\b(anterior|hist[oó]ric[oa]|pr[eé]vi[oa]|comparativo)\b", trecho
            )
        ):
            datas = {contexto}
        origem_data = "data explícita no trecho do resultado"
        if not datas and not re.search(
            r"(?i)\b(anterior|hist[oó]ric[oa]|pr[eé]vi[oa]|comparativo)\b"
            r"|\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}",
            trecho,
        ):
            # Só um cabeçalho explícito na mesma página, nunca a emissão.
            datas = datas_explicitas(paginas[linha["pagina"]])
            origem_data = "única data de coleta explícita na página"
        if len(datas) == 1:
            resultado.at[indice, "data_coleta"] = next(iter(datas))
            resultado.at[indice, "origem_data"] = "coleta explícita"
        elif not datas and not re.search(
            r"(?i)\b(anterior|hist[oó]ric[oa]|pr[eé]vi[oa]|comparativo)\b", trecho
        ):
            # Atendimento serve apenas como sugestão sinalizada, nunca como comprovação.
            atendimento = set(
                re.findall(
                    r"(?i)\batend(?:imento)?\.?\s*:\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
                    paginas[linha["pagina"]],
                )
            )
            if len(atendimento) == 1:
                try:
                    resultado.at[indice, "data_coleta"] = normalizar_data_coleta(
                        next(iter(atendimento))
                    ).isoformat()
                    resultado.at[indice, "origem_data"] = (
                        "atendimento — confirmar coleta"
                    )
                    origem_data = "data sugerida pelo atendimento; confirmar se corresponde à coleta"
                except ValueError:
                    pass
        alvo = PARAMETROS[linha["parametro"]][1]
        valor, unidade, nota_unidade = padronizar_resultado(
            linha["parametro"], linha["valor_confirmado"], linha["unidade_origem"]
        )
        resultado.at[indice, "valor_confirmado"] = valor
        resultado.at[indice, "unidade_confirmada"] = unidade
        valido = (
            resultado.at[indice, "data_coleta"] != ""
            and resultado.at[indice, "unidade_confirmada"] == alvo
            and valor is not None
            and math.isfinite(float(valor))
            and float(valor) > 0
        )
        resultado.at[indice, "usar"] = valido
        resultado.at[indice, "observacao"] = (
            f"Sugestão automática para revisão: {origem_data}. {nota_unidade}"
            if valido
            else "Preenchimento incompleto ou ambíguo: confira data, valor e unidade."
        )
    return resultado
