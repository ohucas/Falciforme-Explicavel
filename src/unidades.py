import re

from .analise import PARAMETROS


def padronizar_resultado(parametro, valor, unidade):
    """Retorna valor, unidade e nota. Unidades desconhecidas permanecem pendentes."""
    alvo = PARAMETROS[parametro][1]
    u = re.sub(r"\s+", "", str(unidade)).casefold().replace("μ", "µ")
    u = u.replace("/ul", "/µl").replace("/mm3", "/µl").replace("/mm³", "/µl")
    if u == alvo.casefold():
        return valor, alvo, ""
    if parametro == "hemacias" and u in {"10^6/µl", "milhões/µl", "milhoes/µl"}:
        return valor, alvo, "10^6/µL corresponde a milhões/µL; valor preservado."
    if parametro == "leucocitos" and u in {"/µl", "células/µl", "celulas/µl"}:
        return valor, alvo, "Contagem por µL, sem mudança de escala."
    if parametro == "plaquetas" and u == "/µl" and valor is not None:
        return valor / 1000, alvo, "Contagem por µL dividida por 1000 para mil/µL."
    if parametro == "plaquetas" and u in {"10^3/µl", "mil/µl"}:
        return valor, alvo, "Unidade equivalente a mil/µL; valor preservado."
    return valor, str(unidade), "Unidade não padronizada automaticamente."
