"""Leitura documental local e extração conservadora de candidatos, sem LLM.
Nada é considerado um resultado confirmado antes da revisão humana.
"""

from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import hashlib
import re
import xml.etree.ElementTree as ET
import pandas as pd
from .datas import normalizar_data_coleta
from .analise import PARAMETROS
from .linhas_documentais import linhas_de_resultados
from .ocr_local import reconhecer_imagem, reconhecer_pagina_pdf

COLUNAS = [
    "usar",
    "documento",
    "pagina",
    "parametro",
    "valor_texto",
    "valor_confirmado",
    "unidade_origem",
    "unidade_confirmada",
    "data_coleta",
    "data_contexto",
    "trecho",
    "observacao",
]
ALIASES = {
    "hemoglobina": r"hemoglobina(?:\s+total)?|hb(?![a-zA-Z0-9])",
    "hematocrito": r"hemat[oó]crito|ht(?![a-zA-Z0-9])",
    "hemacias": r"hem[aá]cias|eritr[oó]citos|rbc",
    "vcm": r"v\.?\s*c\.?\s*m\.?",
    "hcm": r"h\.?\s*c\.?\s*m\.?",
    "chcm": r"c\.?\s*h\.?\s*c\.?\s*m\.?",
    "rdw": r"rdw(?:[- ]cv)?",
    "leucocitos": r"leuc[oó]citos(?:\s+totais)?|wbc",
    "plaquetas": r"plaquetas|plt",
}
DATE_RX = r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b"


def ler_documento(conteudo, nome, documento="Documento 1"):
    if not conteudo or len(conteudo) > 5_000_000:
        raise ValueError("Documento vazio ou maior que 5 MB.")
    ext = Path(nome).suffix.lower()
    avisos = []
    paginas = []
    if ext == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(BytesIO(conteudo))
            if reader.is_encrypted:
                raise ValueError(
                    "PDF protegido: forneça uma cópia acessível ou cole o texto revisado."
                )
            if len(reader.pages) > 30:
                raise ValueError("Limite de 30 páginas por PDF nesta versão.")
            for n, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                # Reconstrói as linhas pela posição visual para laudos tabulares.
                try:
                    layout = page.extract_text(extraction_mode="layout") or ""
                except Exception:
                    layout = ""
                if layout.strip():
                    text = layout
                if not text.strip():
                    if n <= 5:
                        try:
                            text = reconhecer_pagina_pdf(conteudo, n - 1)
                            avisos.append(
                                f"Página {n} lida por OCR local; confira caracteres, números e datas."
                            )
                        except ValueError as erro:
                            avisos.append(f"Página {n}: {erro}")
                    else:
                        avisos.append(
                            f"Página {n} sem texto; OCR limitado às cinco primeiras páginas. Envie esta página separadamente."
                        )
                paginas.append({"pagina": n, "texto": text})
        except ValueError:
            raise
        except Exception:
            raise ValueError(
                "Não foi possível ler o PDF. Confira o arquivo e os avisos de leitura."
            ) from None
    elif ext in {".png", ".jpg", ".jpeg"}:
        from PIL import Image

        try:
            with Image.open(BytesIO(conteudo)) as imagem:
                texto = reconhecer_imagem(imagem)
            paginas = [{"pagina": 1, "texto": texto}]
            avisos.append(
                "Imagem lida por OCR local; confira todos os valores e datas."
            )
        except (OSError, Image.DecompressionBombError):
            raise ValueError("Imagem inválida ou grande demais para leitura.") from None
    elif ext == ".docx":
        try:
            with ZipFile(BytesIO(conteudo)) as z:
                if sum(i.file_size for i in z.infolist()) > 20_000_000:
                    raise ValueError("DOCX descompactado excede o limite de segurança.")
                raw = z.read("word/document.xml")
                if len(raw) > 3_000_000:
                    raise ValueError("Conteúdo DOCX muito extenso.")
            xml = ET.fromstring(raw)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            # Não executar macros nem carregar relações externas.
            paras = [
                " ".join(t.text or "" for t in p.findall(".//w:t", ns))
                for p in xml.findall(".//w:p", ns)
            ]
            paginas = [{"pagina": 1, "texto": "\n".join(paras)}]
            avisos.append(
                "DOCX: somente o corpo e as tabelas; cabeçalhos, rodapés, imagens e paginação não são recuperados. Página 1 significa corpo do documento."
            )
        except (BadZipFile, KeyError, ET.ParseError):
            raise ValueError("DOCX inválido ou ilegível.") from None
    elif ext == ".txt":
        if len(conteudo) > 300_000:
            raise ValueError("Limite de 300 KB para texto.")
        try:
            text = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Salve o TXT em UTF-8.") from None
        paginas = [{"pagina": 1, "texto": text}]
    else:
        raise ValueError(
            "Use PDF, DOCX, TXT, PNG ou JPG. Imagens exigem OCR local instalado."
        )
    if sum(len(p["texto"]) for p in paginas) > 300_000:
        raise ValueError("Texto extraído excede o limite de 300 mil caracteres.")
    if not any(p["texto"].strip() for p in paginas):
        avisos.append(
            "Nenhum texto disponível. Cole uma transcrição conferida; o documento não foi compreendido automaticamente."
        )
    return {
        "id": documento,
        "paginas": paginas,
        "avisos": avisos,
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }


def numero_candidato(token):
    # Separador único com três casas pode ser decimal ou milhar: não adivinhar.
    if re.fullmatch(r"\d+[.,]\d{3}", token):
        return None, "Separador ambíguo; confira e digite o valor numérico."
    if "." in token and "," in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    else:
        token = token.replace(",", ".")
    try:
        return float(token), "Conferir transcrição, unidade e contexto."
    except ValueError:
        return None, "Número ambíguo; transcreva manualmente."


def candidatos(doc):
    rows = []
    from .preenchimento import datas_explicitas

    for page in doc["paginas"]:
        contexto = ""
        resultado_no_bloco = False
        datas_pendentes = set()
        for line in linhas_de_resultados(page["texto"], ALIASES):
            if not line.strip():
                continue
            datas_linha = datas_explicitas(line)
            if datas_linha:
                if resultado_no_bloco:
                    datas_pendentes = set()
                datas_pendentes.update(datas_linha)
                contexto = (
                    next(iter(datas_pendentes)) if len(datas_pendentes) == 1 else ""
                )
                resultado_no_bloco = False
            # A coluna de referência posterior ao resultado não apaga a observação.
            line = re.split(r"(?i)\b(?:valores?\s+de\s+)?refer[eê]ncia\b", line)[0]
            # Ranges, condições e metas não são observações. Exclusão conservadora, não compreensão semântica.
            if re.search(
                r"(?i)\b(meta|alvo|refer[eê]ncia|se|caso|objetivo|exemplo)\b|[<>≤≥]",
                line,
            ):
                continue
            aliases_pagina = dict(ALIASES)
            if re.search(r"(?i)\bleucograma\b", page["texto"]):
                aliases_pagina["leucocitos"] += r"|contagem\s+global"
            for param, alias in aliases_pagina.items():
                if param == "rdw" and re.search(r"(?i)rdw[- ]sd", line):
                    continue
                pattern = (
                    rf"(?i)(?<![\w.])(?:{alias})\s*(?:[:=]|de)?\s*"
                    rf"[☑☒✓✔✗✘❎❌■↑↓*]*\s*(\d+(?:[.,]\d+)*)(?!\w)"
                )
                for match in re.finditer(pattern, line):
                    raw = match.group(1)
                    # Não converter faixa do tipo “Hb 8-10” em observação.
                    if re.match(r"\s*(?:[-–]|a\s)\s*\d", line[match.end() :]):
                        continue
                    val, note = numero_candidato(raw)
                    tail = line[match.end() :]
                    unit_match = re.match(
                        r"(?i)\s*(10\s*\^\s*[36]/(?:µ[lL]|μ[lL]|u[lL]|mm[³3])|g/d[lL]|f[lL]|p[gG]|%|(?:milh[oõ]es|mil|c[eé]lulas)/(?:µ[lL]|u[lL]|mm[³3])|/(?:µ[lL]|u[lL]|mm[³3]))",
                        tail,
                    )
                    unit = unit_match.group(1) if unit_match else ""
                    resultado_no_bloco = True
                    rows.append(
                        {
                            "usar": False,
                            "documento": doc["id"],
                            "pagina": page["pagina"],
                            "parametro": param,
                            "valor_texto": raw,
                            "valor_confirmado": val,
                            "unidade_origem": unit,
                            "unidade_confirmada": unit,
                            "data_coleta": "",
                            "data_contexto": contexto,
                            "trecho": line.strip()[:350],
                            "observacao": note
                            + " Data da coleta não atribuída automaticamente.",
                        }
                    )
    return pd.DataFrame(rows, columns=COLUNAS)


def datas_mencionadas(doc):
    return sorted(
        set(re.findall(DATE_RX, "\n".join(p["texto"] for p in doc["paginas"])))
    )


def montar_tabela(confirmados):
    """Inclui apenas candidatos selecionados com data e unidade explicitamente revistas."""
    df = confirmados.copy()
    selected = df[df["usar"].eq(True)]
    if selected.empty:
        return pd.DataFrame(columns=["data_coleta", *PARAMETROS, "peso_kg"])
    registros = {}
    for _, r in selected.iterrows():
        p = r["parametro"]
        if p not in PARAMETROS:
            raise ValueError("Parâmetro não suportado.")
        try:
            s = normalizar_data_coleta(r["data_coleta"]).isoformat()
        except ValueError as erro:
            raise ValueError(
                f"{r.get('documento', 'Documento')}, {p}: {erro}. "
                "Confirme a data da COLETA em AAAA-MM-DD ou DD/MM/AAAA."
            ) from None
        target = PARAMETROS[p][1]
        if str(r["unidade_confirmada"]).strip() != target:
            raise ValueError(
                f"{p}: confirme/transcreva na unidade {target}. Não há conversão automática."
            )
        try:
            value = float(r["valor_confirmado"])
        except (ValueError, TypeError):
            raise ValueError("Valor ausente ou não numérico.") from None
        import math

        if not math.isfinite(value) or value <= 0:
            raise ValueError("Resultado deve ser positivo e finito.")
        row = registros.setdefault(
            s,
            {
                "data_coleta": s,
                **{p: float("nan") for p in PARAMETROS},
                "peso_kg": float("nan"),
            },
        )
        if not pd.isna(row[p]):
            raise ValueError(
                f"Dois resultados selecionados para {p} na mesma data. Resolva a duplicação na conferência; não faremos média ou escolha automática."
            )
        row[p] = value
    return pd.DataFrame([registros[k] for k in sorted(registros)])


def sintese_documental(registros):
    lines = [
        "SÍNTESE DOCUMENTAL CONFERIDA — PROTÓTIPO 0.2",
        "Compilação de trechos selecionados pelo usuário; não é novo parecer, diagnóstico ou prescrição.",
        "Uma menção histórica não demonstra sintoma ou tratamento atual. Ausência de menção não é ausência de doença.",
        "Solicite revisão médica. Não adie atendimento por sintomas atuais para ler documentos antigos.",
        "",
    ]
    for reg in registros:
        lines += [
            reg["id"],
            "Data de emissão informada: "
            + (reg.get("data_emissao") or "Não informada"),
            "Datas mencionadas (papel temporal não determinado): "
            + (", ".join(reg.get("datas", [])) or "Nenhuma recuperada"),
            "Trechos selecionados e conferidos pelo usuário:",
            reg.get("trechos") or "Nenhum trecho selecionado.",
            "Limites de leitura: " + "; ".join(reg.get("avisos", [])),
            "",
        ]
    return "\n".join(lines)
