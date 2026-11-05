import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


def reconhecer_imagem(imagem):
    executavel = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if not executavel:
        comum = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        executavel = str(comum) if comum.is_file() else None
    if not executavel:
        raise ValueError(
            "OCR indisponível: instale o Tesseract local e configure TESSERACT_CMD ou PATH."
        )
    if imagem.width * imagem.height > 20_000_000:
        raise ValueError("Imagem excede o limite de 20 milhões de pixels para OCR.")
    with TemporaryDirectory(prefix="falciforme_ocr_") as pasta:
        entrada = Path(pasta) / "pagina.png"
        imagem.convert("RGB").save(entrada)
        try:
            idiomas = subprocess.run(
                [executavel, "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.splitlines()
            idioma = (
                "por+eng"
                if "por" in idiomas and "eng" in idiomas
                else ("por" if "por" in idiomas else "eng")
            )
            retorno = subprocess.run(
                [executavel, str(entrada), "stdout", "-l", idioma, "--psm", "6"],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return retorno.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as erro:
            raise ValueError(
                "OCR não concluído: confira a instalação, os idiomas e a qualidade do documento."
            ) from erro


def reconhecer_pagina_pdf(conteudo, indice):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ValueError("Para OCR de PDF, instale requirements-ocr.txt.") from None
    documento = pdfium.PdfDocument(conteudo)
    try:
        pagina = documento[indice]
        try:
            largura, altura = pagina.get_size()
            if largura * altura * 4 > 20_000_000:
                raise ValueError("Página grande demais para OCR.")
            bitmap = pagina.render(scale=2)
            try:
                return reconhecer_imagem(bitmap.to_pil())
            finally:
                bitmap.close()
        finally:
            pagina.close()
    finally:
        documento.close()
