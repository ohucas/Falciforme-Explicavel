"""Formato de hemograma com símbolos e abreviações; todos os valores são fictícios."""

import unittest

from src.documentos import ler_documento, candidatos, montar_tabela
from src.preenchimento import sugerir_preenchimento


class TestLayoutHemograma(unittest.TestCase):
    def dados(self, cabecalho="Coleta: 02/04/2026"):
        texto = cabecalho + "\n" + "\n".join([
            "Hemograma",
            "Resultado                 Intervalo de Referência",
            "Hemácias ❎ 3,25 10^6/µL    4,50 a 5,50 10^6/µL",
            "Hemoglobina ☑ 9,4 g/dL     13,0 a 17,0 g/dL",
            "Hematócrito ❎ 28,4 %       40,0 a 50,0 %",
            "H.C.M. ❎ 29,1 pg           27,0 a 32,0 pg",
            "V.C.M. ☑ 90,5 fL           83,0 a 101,0 fL",
            "C.H.C.M ☑ 32,1 g/dL        31,0 a 35,0 g/dL",
            "RDW ❎ 18,2 %               11,6 a 14,0 %",
            "Leucograma",
            "Contagem Global ☑ 7500 /µL 4000 a 10000 /µL",
            "Plaquetas ☑ 280000 /µL     150000 a 450000 /µL",
        ])
        doc = ler_documento(texto.encode(), "ficticio.txt")
        return sugerir_preenchimento(doc, candidatos(doc))

    def test_nove_parametros_sem_capturar_referencias(self):
        dados = self.dados()
        self.assertEqual(len(dados), 9)
        self.assertTrue(dados.usar.all())
        tabela = montar_tabela(dados)
        self.assertEqual(tabela.iloc[0].hemoglobina, 9.4)
        self.assertEqual(tabela.iloc[0].plaquetas, 280)
        self.assertEqual(tabela.iloc[0].hemacias, 3.25)
        self.assertEqual(tabela.iloc[0].leucocitos, 7500)

    def test_hcm_nao_duplica_chcm(self):
        dados = self.dados()
        self.assertEqual(int(dados.parametro.eq("hcm").sum()), 1)
        self.assertEqual(int(dados.parametro.eq("chcm").sum()), 1)

    def test_atendimento_e_identificado_como_sugestao(self):
        dados = self.dados("Nasc.: 02/07/2000     Atend.: 02/04/2026")
        self.assertTrue(dados.data_coleta.eq("2026-04-02").all())
        self.assertTrue(dados.origem_data.eq("atendimento — confirmar coleta").all())

    def test_nascimento_e_liberacao_nao_viram_coleta(self):
        dados = self.dados("Nasc.: 02/07/2000\nLiberação: 03/04/2026")
        self.assertTrue(dados.data_coleta.eq("").all())
        self.assertFalse(dados.usar.any())

    def test_global_sem_leucograma_nao_e_leucocitos(self):
        doc = ler_documento("Contagem Global ☑ 7500 /µL".encode(), "ficticio.txt")
        self.assertTrue(candidatos(doc).empty)


if __name__ == "__main__":
    unittest.main()
