from datetime import date, datetime
import re

import pandas as pd


def normalizar_data_coleta(valor, hoje=None):
    """Aceita data do calendário, ISO ou DD/MM/AAAA e devolve uma data real."""
    hoje = hoje or date.today()
    if valor is None or pd.isna(valor) or str(valor).strip() == "":
        raise ValueError("data de coleta ausente")
    if isinstance(valor, datetime):
        resultado = valor.date()
    elif isinstance(valor, date):
        resultado = valor
    else:
        texto = str(valor).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
            formato = "%Y-%m-%d"
        elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto):
            formato = "%d/%m/%Y"
        else:
            raise ValueError("use AAAA-MM-DD ou DD/MM/AAAA")
        try:
            resultado = datetime.strptime(texto, formato).date()
        except ValueError:
            raise ValueError("data de coleta inválida no calendário") from None
    if resultado > hoje:
        raise ValueError("uma coleta não pode ter data futura")
    return resultado


def remover_linhas_vazias(tabela):
    """Ignora somente linhas inteiramente vazias; não descarta linhas incompletas."""
    vazias = tabela.apply(
        lambda coluna: coluna.map(
            lambda valor: pd.isna(valor)
            or (isinstance(valor, str) and not valor.strip())
        )
    ).all(axis=1)
    return tabela.loc[~vazias].copy()
