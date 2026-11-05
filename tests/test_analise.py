import unittest
from datetime import date
import pandas as pd
from src.analise import (
    validar_exames,
    comparar,
    referencias_vazias,
    sinais_alerta,
    relatorio_texto,
)


def exemplo():
    return pd.read_csv("exemplos/tres_exames_ficticios.csv")


class TestAnalise(unittest.TestCase):
    def test_ordena_e_compara_sem_incluir_atual_na_media(self):
        d = exemplo().iloc[::-1]
        r = comparar(d).set_index("parametro").loc["hemoglobina"]
        self.assertAlmostEqual(r.media_dois_anteriores, 9.0)
        self.assertAlmostEqual(r.diferenca, 0.4)
        self.assertEqual(r.faixa_laboratorio, "Não informado")

    def test_duas_coletas_comparam_sem_exigir_terceira(self):
        r = comparar(exemplo().iloc[1:]).set_index("parametro").loc["hemoglobina"]
        self.assertIn("aumento entre as duas coletas", r.explicacao)
        self.assertNotIn("insuficientes", r.explicacao)
        self.assertAlmostEqual(r.diferenca, 0.4)
        self.assertTrue(pd.isna(r.antigo))
        self.assertTrue(pd.isna(r.media_dois_anteriores))

    def test_duas_coletas_igualdade_reducao_e_ausencia(self):
        d = exemplo().iloc[:2].copy()
        d["hemoglobina"] = [10.0, 10.0]
        r = comparar(d).iloc[0]
        self.assertIn("mesmo valor nas duas coletas", r.explicacao)
        d["hemoglobina"] = [10.0, 9.0]
        self.assertIn("redução entre as duas coletas", comparar(d).iloc[0].explicacao)
        d.loc[d.index[0], "hemoglobina"] = float("nan")
        r = comparar(d).iloc[0]
        self.assertIn("insuficientes deste parâmetro nas duas", r.explicacao)
        self.assertTrue(pd.isna(r.diferenca))

    def test_validacao_e_idempotente(self):
        d = validar_exames(exemplo())
        pd.testing.assert_frame_equal(d, validar_exames(d))
        self.assertEqual(len(comparar(d)), 9)

    def test_datas_duplicadas_futuras_e_quantidade(self):
        d = exemplo()
        d.loc[1, "data_coleta"] = d.loc[0, "data_coleta"]
        with self.assertRaises(ValueError):
            validar_exames(d)
        d = exemplo()
        d.loc[2, "data_coleta"] = "2999-01-01"
        with self.assertRaises(ValueError):
            validar_exames(d)
        with self.assertRaises(ValueError):
            validar_exames(exemplo().iloc[:2])

    def test_zero_infinito_e_identificador_rejeitados(self):
        d = exemplo()
        d.loc[0, "hemoglobina"] = 0
        with self.assertRaises(ValueError):
            validar_exames(d)
        d = exemplo()
        d.loc[0, "peso_kg"] = float("inf")
        with self.assertRaises(ValueError):
            validar_exames(d)
        d = exemplo()
        d["nome"] = "Não deve ser importado"
        with self.assertRaises(ValueError):
            validar_exames(d)

    def test_ausencia_nao_e_imputada(self):
        d = exemplo()
        d.loc[0, "hemoglobina"] = float("nan")
        r = comparar(d).set_index("parametro").loc["hemoglobina"]
        self.assertTrue(pd.isna(r.media_dois_anteriores))
        self.assertIn("insuficientes", r.explicacao)

    def test_basal_nao_e_automatico_e_exige_confirmacao(self):
        ref = referencias_vazias()
        ref.loc[0, "basal_individual"] = 9.0
        with self.assertRaises(ValueError):
            comparar(exemplo(), ref)
        r = comparar(exemplo(), ref, True).set_index("parametro").loc["hemoglobina"]
        self.assertAlmostEqual(r.diferenca_basal, 0.3)

    def test_faixa_laboratorio_nao_muda_com_peso(self):
        ref = referencias_vazias()
        ref.loc[0, ["min_laboratorio", "max_laboratorio"]] = [10, 15]
        d = exemplo()
        a = comparar(d, ref)
        d["peso_kg"] = 100
        b = comparar(d, ref)
        self.assertEqual(a.iloc[0].faixa_laboratorio, b.iloc[0].faixa_laboratorio)
        self.assertEqual(a.iloc[0].faixa_laboratorio, "Abaixo da faixa informada")

    def test_referencias_invertidas_rejeitadas(self):
        ref = referencias_vazias()
        ref.loc[0, ["min_laboratorio", "max_laboratorio"]] = [15, 10]
        with self.assertRaises(ValueError):
            comparar(exemplo(), ref)

    def test_alerta_febre_e_sintoma_independe_do_exame(self):
        self.assertTrue(sinais_alerta(38.5))
        self.assertFalse(sinais_alerta(38.4))
        self.assertTrue(sinais_alerta(None, ["Dor no peito"]))

    def test_relatorio_tem_fontes_e_nao_declara_seguranca(self):
        d = exemplo()
        r = comparar(d)
        txt = relatorio_texto({"subtipo": "Não informado"}, d, r, [], [])
        self.assertIn("NÃO significa ausência de risco", txt)
        self.assertIn("F1:", txt)
        self.assertIn("não estima probabilidades", txt)


if __name__ == "__main__":
    unittest.main()
