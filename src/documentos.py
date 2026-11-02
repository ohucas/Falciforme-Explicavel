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
from .analise import PARAMETROS

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
    "trecho",
    "observacao",
]
ALIASES = {
    "hemoglobina": r"hemoglobina(?:\s+total)?|hb(?![a-zA-Z0-9])",
    "hematocrito": r"hemat[oó]crito|ht(?![a-zA-Z0-9])",
    "hemacias": r"hem[aá]cias|eritr[oó]citos",
    "vcm": r"vcm",
    "hcm": r"hcm",
    "chcm": r"chcm",
    "rdw": r"rdw(?:[- ]cv)?",
    "leucocitos": r"leuc[oó]citos(?:\s+totais)?",
    "plaquetas": r"plaquetas",
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
                if not text.strip():
                    avisos.append(
                        f"Página {n} sem texto extraível: pode exigir OCR ou transcrição."
                    )
                paginas.append({"pagina": n, "texto": text})
        except ValueError:
            raise
        except Exception:
            raise ValueError(
                "Não foi possível ler o PDF. Confira o arquivo; não há OCR nesta versão."
            ) from None
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
            "Use PDF com texto, DOCX ou TXT. Fotos e documentos digitalizados precisam de transcrição nesta versão."
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
    for page in doc["paginas"]:
        for line in page["texto"].splitlines():
            if not line.strip():
                continue
            # Ranges, condições e metas não são observações. Exclusão conservadora, não compreensão semântica.
            if re.search(
                r"(?i)\b(meta|alvo|refer[eê]ncia|se|caso|objetivo|exemplo)\b|[<>≤≥]",
                line,
            ):
                continue
            for param, alias in ALIASES.items():
                if param == "rdw" and re.search(r"(?i)rdw[- ]sd", line):
                    continue
                pattern = (
                    rf"(?i)(?<!\w)(?:{alias})\s*(?:[:=]|de)?\s*(\d+(?:[.,]\d+)*)(?!\w)"
                )
                for match in re.finditer(pattern, line):
                    raw = match.group(1)
                    # Não converter faixa do tipo “Hb 8-10” em observação.
                    if re.match(r"\s*(?:[-–]|a\s)\s*\d", line[match.end() :]):
                        continue
                    val, note = numero_candidato(raw)
                    tail = line[match.end() :]
                    unit_match = re.match(
                        r"\s*(g/d[lL]|f[lL]|p[gG]|%|(?:milh[oõ]es|mil|c[eé]lulas)/(?:µ[lL]|u[lL]|mm[³3])|(?:µ[lL]|u[lL]))",
                        tail,
                    )
                    unit = unit_match.group(1) if unit_match else ""
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
        s = str(r["data_coleta"]).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            raise ValueError(
                "Cada resultado selecionado precisa de data de coleta confirmada em AAAA-MM-DD, não apenas a data do relatório."
            )
        try:
            dt = date.fromisoformat(s)
        except ValueError:
            raise ValueError("Data de coleta inválida.") from None
        if dt > date.today():
            raise ValueError("Data de coleta futura.")
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
