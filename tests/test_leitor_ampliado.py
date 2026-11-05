"""Regressões sintéticas para múltiplos layouts e blocos de coleta."""

import unittest
from unittest.mock import patch
from io import BytesIO
from PIL import Image
from src.documentos import ler_documento, candidatos, montar_tabela
from src.preenchimento import sugerir_preenchimento


class TestLeitorAmpliado(unittest.TestCase):
    def test_blocos_distintos_preservam_tres_coletas(self):
        texto = "\n".join(
            f"Coleta: {data}\nHemoglobina {valor} g/dL\nVCM 90 fL"
            for data, valor in [
                ("02/01/2026", "9,0"),
                ("02/04/2026", "9,2"),
                ("02/07/2026", "9,4"),
            ]
        )
        doc = ler_documento(texto.encode(), "exame.txt")
        tabela = montar_tabela(sugerir_preenchimento(doc, candidatos(doc)))
        self.assertEqual(len(tabela), 3)
        self.assertEqual(tabela.hemoglobina.tolist(), [9.0, 9.2, 9.4])

    def test_referencia_apos_resultado_nao_apaga_valor(self):
        doc = ler_documento(
            b"Coleta: 02/04/2026\nHemoglobina 9,2 g/dL Referencia 12-16", "x.txt"
        )
        dados = sugerir_preenchimento(doc, candidatos(doc))
        self.assertEqual(len(dados), 1)
        self.assertEqual(dados.iloc[0].valor_confirmado, 9.2)

    def test_imagem_chama_ocr_local(self):
        b = BytesIO()
        Image.new("RGB", (200, 100), "white").save(b, format="PNG")
        with patch(
            "src.documentos.reconhecer_imagem",
            return_value="Coleta: 02/04/2026\nHemoglobina 9,2 g/dL",
        ):
            doc = ler_documento(b.getvalue(), "exame.png")
        self.assertTrue(sugerir_preenchimento(doc, candidatos(doc)).usar.all())

    def test_ocr_indisponivel_nao_fabrica_resultados(self):
        b = BytesIO()
        Image.new("RGB", (200, 100), "white").save(b, format="PNG")
        with patch(
            "src.documentos.reconhecer_imagem",
            side_effect=ValueError("OCR indisponível"),
        ):
            with self.assertRaisesRegex(ValueError, "OCR indisponível"):
                ler_documento(b.getvalue(), "exame.png")
