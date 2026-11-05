import unittest

from src.documentos import candidatos, ler_documento
from src.preenchimento import sugerir_preenchimento


class TestPreenchimento(unittest.TestCase):
    def extrair(self, texto):
        doc = ler_documento(texto.encode(), "exemplo.txt", "Documento 1")
        return sugerir_preenchimento(doc, candidatos(doc))

    def test_varias_coletas_explicitamente_associadas(self):
        dados = self.extrair(
            "Coleta de 02/04/2026: hemoglobina 9,1 g/dL\n"
            "Coleta de 03/07/2026: hemoglobina 8,9 g/dL"
        )
        self.assertEqual(list(dados.data_coleta), ["2026-04-02", "2026-07-03"])
        self.assertTrue(dados.usar.all())

    def test_emissao_nao_vira_coleta(self):
        dados = self.extrair("Emitido em 02/04/2026\nHemoglobina 9,1 g/dL")
        self.assertEqual(dados.iloc[0].data_coleta, "")
        self.assertFalse(dados.usar.any())

    def test_cabecalho_unico_da_mesma_pagina(self):
        dados = self.extrair("Data da coleta: 02/04/2026\nHemoglobina 9,1 g/dL")
        self.assertEqual(dados.iloc[0].data_coleta, "2026-04-02")
        self.assertTrue(dados.usar.all())

    def test_varias_datas_sem_associacao_nao_sao_adivinhadas(self):
        dados = self.extrair(
            "Coleta: 02/04/2026\nColeta: 03/07/2026\nHemoglobina 9,1 g/dL"
        )
        self.assertFalse(dados.usar.any())

    def test_resultado_historico_nao_herda_data_do_cabecalho(self):
        dados = self.extrair(
            "Data da coleta: 02/04/2026\nHemoglobina anterior 9,1 g/dL"
        )
        # O extrator conservador pode nem reconhecer a frase histórica.
        self.assertTrue(dados.empty or not dados.usar.any())

    def test_sem_unidade_nao_seleciona(self):
        dados = self.extrair("Coleta: 02/04/2026\nHemoglobina 9,1")
        self.assertFalse(dados.usar.any())


if __name__ == "__main__":
    unittest.main()
