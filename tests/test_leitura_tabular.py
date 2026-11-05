"""Casos que falhavam com parâmetros e valores extraídos fora da mesma linha."""

from io import BytesIO
import unittest

from reportlab.pdfgen.canvas import Canvas

from src.documentos import candidatos, ler_documento
from src.preenchimento import sugerir_preenchimento


class TestLeituraTabular(unittest.TestCase):
    def test_rotulo_valor_e_unidade_em_linhas_separadas(self):
        texto = "Data da coleta:\n02/04/2026\nHemoglobina\n9,1\ng/dL\nVCM\n82\nfL"
        doc = ler_documento(texto.encode(), "exemplo.txt")
        dados = sugerir_preenchimento(doc, candidatos(doc))
        self.assertEqual(set(dados.parametro), {"hemoglobina", "vcm"})
        self.assertTrue(dados.usar.all())
        self.assertTrue(dados.data_coleta.eq("2026-04-02").all())

    def test_nao_atravessa_outro_parametro(self):
        doc = ler_documento(
            b"Coleta: 02/04/2026\nHemoglobina\nVCM\n82 fL", "exemplo.txt"
        )
        dados = candidatos(doc)
        self.assertNotIn("hemoglobina", dados.parametro.tolist())

    def test_faixa_de_referencia_nao_vira_resultado(self):
        doc = ler_documento(b"Hemoglobina\n8-10 g/dL", "exemplo.txt")
        self.assertTrue(candidatos(doc).empty)

    def test_pdf_desenhado_por_colunas_recupera_linhas_visuais(self):
        memoria = BytesIO()
        pdf = Canvas(memoria)
        pdf.drawString(50, 790, "Data da coleta: 02/04/2026")
        # Os rótulos são gravados antes da coluna de valores no arquivo PDF.
        pdf.drawString(50, 750, "Hemoglobina")
        pdf.drawString(50, 720, "VCM")
        pdf.drawString(250, 750, "9,1 g/dL")
        pdf.drawString(250, 720, "82 fL")
        pdf.save()
        doc = ler_documento(memoria.getvalue(), "exame.pdf")
        dados = sugerir_preenchimento(doc, candidatos(doc))
        self.assertEqual(len(dados), 2)
        self.assertTrue(dados.usar.all())


if __name__ == "__main__":
    unittest.main()
