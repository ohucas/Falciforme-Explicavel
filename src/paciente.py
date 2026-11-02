"""Cadastro separado das variáveis de pesquisa e do histórico laboratorial."""

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class Paciente:
    nome: str = ""
    idade: float | None = None
    peso_kg: float | None = None
    altura_cm: float | None = None
    sexo: str = "Não informado"
    subtipo: str = "Outro / não informado"
    cid_versao: str = "CID-10"
    cid_codigo: str = ""
    cid_descricao: str = ""


def validar_paciente(paciente):
    """Valida formato; não confirma diagnóstico nem adequação clínica da CID."""
    limites = {"idade": (0, 120), "peso_kg": (0, 500), "altura_cm": (0, 260)}
    for campo, (minimo, maximo) in limites.items():
        valor = getattr(paciente, campo)
        if valor is None:
            continue
        if not math.isfinite(valor) or valor < minimo or valor > maximo:
            raise ValueError(f"Confira {campo}: valor fora do intervalo suportado.")
        if campo != "idade" and valor == 0:
            raise ValueError(f"{campo} deve ser positivo ou ficar ausente.")
    if len(paciente.nome) > 160:
        raise ValueError("Nome limitado a 160 caracteres.")
    if len(paciente.cid_codigo) > 30 or len(paciente.cid_descricao) > 300:
        raise ValueError("Confira o tamanho dos campos de CID.")
    return paciente


def contexto_numerico(paciente, hidroxiureia):
    """Nome e CID livre nunca entram automaticamente nas features."""
    return {
        "idade": paciente.idade,
        "peso_kg": paciente.peso_kg,
        "altura_cm": paciente.altura_cm,
        "hidroxiureia": {"Sim": 1.0, "Não": 0.0}.get(hidroxiureia),
    }
