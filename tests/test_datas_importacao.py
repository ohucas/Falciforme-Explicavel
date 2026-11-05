"""Regressões do fluxo de datas e da comparação de múltiplos documentos."""

from datetime import date, datetime
from io import BytesIO
import unittest

import pandas as pd
from reportlab.pdfgen.canvas import Canvas

from src.analise import PARAMETROS, comparar, vazio
from src.datas import normalizar_data_coleta
from src.documentos import candidatos, ler_documento, montar_tabela
from src.historico import validar_historico


class TestDatasImportacao(unittest.TestCase):
    def test_formatos_e_objetos_de_data(self):
        for valor in [
            "2026-04-02",
            "02/04/2026",
            date(2026, 4, 2),
            datetime(2026, 4, 2),
            pd.Timestamp("2026-04-02"),
        ]:
            self.assertEqual(normalizar_data_coleta(valor), date(2026, 4, 2))

    def test_ausente_invalida_futura_e_ambigua(self):
        for valor in [None, pd.NaT, "", "31/02/2026", "02/04/26", "2999-01-01"]:
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    normalizar_data_coleta(valor)

    def test_tabela_vazia_tem_mensagem_especifica(self):
        with self.assertRaisesRegex(ValueError, "Nenhuma coleta preenchida"):
            validar_historico(vazio())

    def test_ignora_apenas_linhas_inteiramente_vazias(self):
        tabela = vazio()
        tabela.loc[0, ["data_coleta", "hemoglobina"]] = ["02/04/2026", 9.1]
        tabela.loc[1, ["data_coleta", "hemoglobina"]] = ["03/07/2026", 8.9]
        resultado = validar_historico(tabela)
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado.data_coleta.iloc[0], pd.Timestamp("2026-04-02"))

    def test_linha_com_resultado_e_sem_data_nao_desaparece(self):
        tabela = vazio()
        tabela.loc[0, ["data_coleta", "hemoglobina"]] = ["02/04/2026", 9.1]
        tabela.loc[1, "hemoglobina"] = 8.9
        with self.assertRaisesRegex(ValueError, "Coleta 2: data de coleta ausente"):
            validar_historico(tabela)

    def test_mesma_data_em_dois_formatos_e_duplicada(self):
        tabela = vazio()
        tabela.loc[0, ["data_coleta", "hemoglobina"]] = ["02/04/2026", 9.1]
        tabela.loc[1, ["data_coleta", "hemoglobina"]] = ["2026-04-02", 8.9]
        with self.assertRaisesRegex(ValueError, "datas de coleta devem ser diferentes"):
            validar_historico(tabela)

    def test_tres_pdfs_com_datas_diferentes(self):
        partes = []
        for indice, (data, hb) in enumerate(
            [("01/10/2026", 9.3), ("02/04/2026", 9.1), ("03/07/2026", 8.9)], 1
        ):
            buffer = BytesIO()
            pdf = Canvas(buffer)
            pdf.drawString(50, 780, "DOCUMENTO FICTICIO")
            pdf.drawString(50, 750, "Coleta: " + data)
            pdf.drawString(50, 720, f"Hemoglobina {hb} g/dL")
            pdf.save()
            doc = ler_documento(
                buffer.getvalue(), f"exame{indice}.pdf", f"Doc {indice}"
            )
            linhas = candidatos(doc)
            self.assertFalse(linhas.empty)
            self.assertTrue(linhas.data_coleta.eq("").all())
            self.assertFalse(linhas.usar.any())
            linhas["usar"] = True
            linhas["data_coleta"] = data
            linhas["unidade_confirmada"] = linhas.parametro.map(
                lambda parametro: PARAMETROS[parametro][1]
            )
            partes.append(linhas)
        tabela = montar_tabela(pd.concat(partes, ignore_index=True))
        resultado = validar_historico(tabela)
        self.assertEqual(len(resultado), 3)
        comparacao = comparar(resultado).set_index("parametro")
        self.assertAlmostEqual(comparacao.loc["hemoglobina", "atual"], 9.3)
        self.assertAlmostEqual(comparacao.loc["hemoglobina", "diferenca"], 0.4)


if __name__ == "__main__":
    unittest.main()
