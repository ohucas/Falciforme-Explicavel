from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import unittest
from src.documentos import (
    ler_documento,
    candidatos,
    montar_tabela,
    sintese_documental,
    datas_mencionadas,
)


class TestDocumentos(unittest.TestCase):
    def setUp(self):
        self.doc = ler_documento(
            Path("exemplos/relatorio_ficticio.txt").read_bytes(), "relatorio.txt"
        )

    def test_numero_sem_data_nao_vira_coleta(self):
        c = candidatos(self.doc)
        self.assertEqual(len(c), 6)
        self.assertFalse(c.usar.any())
        self.assertTrue(c.data_coleta.eq("").all())
        self.assertTrue(montar_tabela(c).empty)
        c.loc[0, "usar"] = True
        with self.assertRaises(ValueError):
            montar_tabela(c)

    def test_tres_datas_revisadas_e_unidade_obrigatoria(self):
        c = candidatos(self.doc)
        c["usar"] = True
        c["data_coleta"] = [
            "2026-04-02",
            "2026-04-02",
            "2026-07-03",
            "2026-07-03",
            "2026-10-01",
            "2026-10-01",
        ]
        d = montar_tabela(c)
        self.assertEqual(len(d), 3)
        self.assertAlmostEqual(d.hemoglobina.iloc[-1], 9.3)
        self.assertTrue(d.vcm.isna().all())
        c.loc[0, "unidade_confirmada"] = ""
        with self.assertRaises(ValueError):
            montar_tabela(c)

    def test_data_emissao_nao_associada_automaticamente(self):
        self.assertIn("05/10/2026", datas_mencionadas(self.doc))
        self.assertTrue(candidatos(self.doc).data_coleta.eq("").all())

    def test_duplicatas_nunca_sao_mescladas(self):
        c = candidatos(self.doc).iloc[[0, 2]].copy()
        c["usar"] = True
        c["data_coleta"] = "2026-04-02"
        with self.assertRaises(ValueError):
            montar_tabela(c)

    def test_condicional_faixa_hemoglobina_fetal_nao_sao_resultado(self):
        doc = ler_documento(
            b"Se Hb < 7, avaliar.\nHbS 80%\nHbF 15%\nHb 8-10 g/dL\nReferencia Hb 7 g/dL\nRDW-SD 40 fL",
            "x.txt",
        )
        self.assertTrue(candidatos(doc).empty)

    def test_separador_ambiguo_exige_numero_revisado(self):
        doc = ler_documento("Leucócitos 9.400 células/µL".encode(), "x.txt")
        c = candidatos(doc)
        self.assertTrue(c.valor_confirmado.isna().all())
        c["usar"] = True
        c["data_coleta"] = "2026-10-01"
        with self.assertRaises(ValueError):
            montar_tabela(c)

    def test_narrativa_sem_numeros_pode_gerar_sintese(self):
        doc = ler_documento(
            "Sem relato de febre naquela consulta. Não é avaliação atual.".encode(),
            "x.txt",
        )
        self.assertTrue(candidatos(doc).empty)
        txt = sintese_documental(
            [
                {
                    "id": "Documento 1",
                    "trechos": "Sem relato de febre naquela consulta.",
                    "datas": [],
                    "avisos": [],
                }
            ]
        )
        self.assertIn("Sem relato de febre", txt)
        self.assertIn("não demonstra sintoma", txt)

    def test_docx_sem_executar_conteudo(self):
        b = BytesIO()
        with ZipFile(b, "w") as z:
            z.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hemoglobina 9,3 g/dL</w:t></w:r></w:p></w:body></w:document>',
            )
        doc = ler_documento(b.getvalue(), "teste.docx")
        self.assertEqual(len(candidatos(doc)), 1)

    def test_pdf_sem_texto_nao_inventa_resultados(self):
        from pypdf import PdfWriter

        w = PdfWriter()
        w.add_blank_page(width=300, height=400)
        b = BytesIO()
        w.write(b)
        doc = ler_documento(b.getvalue(), "digitalizado.pdf")
        self.assertTrue(doc["avisos"])
        self.assertTrue(candidatos(doc).empty)


if __name__ == "__main__":
    unittest.main()


class TestPDFDigital(unittest.TestCase):
    def test_pdf_texto_e_origem(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

        w = PdfWriter()
        p = w.add_blank_page(width=300, height=400)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        p[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 10 300 Td (Hemoglobina 9.3 g/dL) Tj ET")
        p[NameObject("/Contents")] = content
        b = BytesIO()
        w.write(b)
        doc = ler_documento(b.getvalue(), "digital.pdf", "Documento teste")
        c = candidatos(doc)
        self.assertEqual(len(c), 1)
        self.assertEqual(c.iloc[0].documento, "Documento teste")
        self.assertEqual(c.iloc[0].pagina, 1)
        self.assertAlmostEqual(c.iloc[0].valor_confirmado, 9.3)
