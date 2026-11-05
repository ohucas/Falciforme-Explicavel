"""Regressões funcionais da evolução; dados exclusivamente artificiais."""

from datetime import date
from io import BytesIO
import unittest
import numpy as np
import pandas as pd
from pypdf import PdfReader
from src.analise import comparar, referencias_vazias
from src.historico import (
    atributos_temporais,
    contagem_confirmada,
    crises_vazias,
    rotulo_futuro,
    validar_crises,
    validar_historico,
)
from src.paciente import Paciente, contexto_numerico, validar_paciente
from src.reports.pdf import relatorio_pdf
from src.pesquisa.modelos import prever, treinar, validar_dataset
from src.pesquisa.explicacoes import comparar_rankings, explicar


def exames():
    return pd.read_csv("exemplos/tres_exames_ficticios.csv")


def coorte():
    rng = np.random.default_rng(15)
    linhas = []
    for i in range(40):
        for j in range(2):
            linhas.append(
                {
                    "paciente_id": f"FICTICIO_{i:03}",
                    "t0": f"2025-0{j + 1}-01",
                    "fim_acompanhamento": "2025-04-01",
                    "horizonte_dias": 30,
                    "target": i % 2,
                    "idade": 20 + i,
                    "hemoglobina_atual": 8 + (i % 2) + rng.normal(0, 0.4),
                    "hemoglobina_delta": rng.normal(0, 0.2),
                }
            )
    return pd.DataFrame(linhas)


class TestEvolucao(unittest.TestCase):
    def test_historico_flexivel_e_compatibilidade(self):
        d = exames()
        extra = d.iloc[-1:].copy()
        extra["data_coleta"] = "2026-10-20"
        hist = validar_historico(pd.concat([d, extra]))
        self.assertEqual(len(hist), 4)
        self.assertAlmostEqual(comparar(hist).iloc[0].anterior, 9.3)
        self.assertEqual(len(comparar(d.iloc[:2])), 9)

    def test_features_nao_olham_futuro(self):
        d = exames()
        f = atributos_temporais(d, "2026-07-03")
        self.assertAlmostEqual(f["hemoglobina_atual"], 8.9)
        self.assertEqual(f["n_coletas"], 2)
        self.assertLess(f["hemoglobina_inclinacao"], 0)

    def test_ausencia_nao_interpolada(self):
        d = exames()
        d.loc[2, "hemoglobina"] = np.nan
        f = atributos_temporais(d)
        self.assertTrue(np.isnan(f["hemoglobina_atual"]))
        self.assertTrue(np.isnan(f["hemoglobina_delta"]))

    def test_evento_mes_nao_inventa_dia(self):
        c = validar_crises(
            pd.DataFrame(
                [
                    {
                        "ano": 2026,
                        "mes": 1,
                        "dia": np.nan,
                        "tipo": "Vaso-oclusiva",
                        "confirmado": True,
                        "fonte": "Prontuário fictício",
                    }
                ]
            )
        )
        self.assertEqual(c.iloc[0].precisao, "Mês")
        self.assertEqual(c.iloc[0].fim, date(2026, 1, 31))
        self.assertTrue(np.isnan(contagem_confirmada(c, "2026-01-15", True)))
        self.assertEqual(contagem_confirmada(c, "2026-02-01", True), 1)

    def test_sem_cobertura_nao_vira_zero(self):
        self.assertTrue(np.isnan(contagem_confirmada(pd.DataFrame(), "2026-01-01")))
        self.assertEqual(contagem_confirmada(pd.DataFrame(), "2026-01-01", True), 0)

    def test_confirmacao_exige_fonte(self):
        with self.assertRaises(ValueError):
            validar_crises(pd.DataFrame([{"ano": 2026, "mes": 1, "confirmado": True}]))

    def test_label_exige_acompanhamento_e_exclui_t0(self):
        self.assertIsNone(rotulo_futuro([], "2026-01-01", "2026-01-20"))
        self.assertEqual(rotulo_futuro(["2026-01-01"], "2026-01-01", "2026-01-31"), 0)
        self.assertEqual(rotulo_futuro(["2026-01-31"], "2026-01-01", "2026-01-31"), 1)

    def test_identidade_fora_das_features(self):
        paciente = validar_paciente(
            Paciente(nome="FICTÍCIO", idade=30, cid_codigo="D57.0")
        )
        self.assertNotIn("nome", contexto_numerico(paciente, "Não informado"))
        self.assertNotIn("cid_codigo", contexto_numerico(paciente, "Não informado"))

    def test_pdf_graficos_e_identificacao_opcional(self):
        d = validar_historico(exames())
        pdf = relatorio_pdf(
            Paciente(nome="NOME_FICTICIO_RESERVADO"),
            d,
            comparar(d),
            referencias_vazias(),
            pd.DataFrame(),
            comentarios="Comentário fictício com acentuação",
        )
        reader = PdfReader(BytesIO(pdf))
        texto = "\n".join(p.extract_text() for p in reader.pages)
        self.assertNotIn("NOME_FICTICIO_RESERVADO", texto)
        self.assertIn("Probabilidade não calculada", texto)
        self.assertIn("Comentário fictício", texto)
        self.assertGreater(sum(len(p.images) for p in reader.pages), 0)

    def test_dataset_sem_nome_e_sem_labels_desconhecidos(self):
        d = coorte()
        d["nome"] = "FICTÍCIO"
        with self.assertRaises(ValueError):
            validar_dataset(d)
        d = coorte()
        d.loc[0, "target"] = np.nan
        with self.assertRaises(ValueError):
            validar_dataset(d)

    def test_rankings_com_empates_e_vetores_nulos(self):
        r = comparar_rankings([1, 0.5, 0], [2, 1, 0], 2)
        self.assertEqual(r["jaccard_top_k"], 1)
        self.assertIsNone(comparar_rankings([0, 0], [0, 0])["spearman"])


class TestPesquisaIntegrada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resultado = treinar(coorte())
        cls.modelo = cls.resultado["modelos"][
            "Clínico e longitudinal | Regressão logística"
        ]

    def test_treinamento_e_inferencia(self):
        p, x, faltantes = prever(
            self.modelo,
            {"idade": 32, "hemoglobina_atual": 8.6, "hemoglobina_delta": 0.1},
        )
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 1)
        self.assertEqual(faltantes, [])
        auditoria = self.resultado["auditoria"]
        self.assertEqual(
            auditoria["pacientes_treino"] + auditoria["pacientes_teste"], 40
        )
        self.assertEqual(len(self.resultado["resultados"]), 9)

    def test_shap_lime_reais(self):
        p, x, _ = prever(
            self.modelo,
            {"idade": 32, "hemoglobina_atual": 8.6, "hemoglobina_delta": 0.1},
        )
        r = explicar(self.modelo, x, amostras_shap=32, amostras_lime=200)
        self.assertEqual(len(r["shap"]), 3)
        self.assertEqual(len(r["lime"]), 3)
        self.assertLess(abs(r["comparacao"]["shap_residuo_aditivo"]), 1e-4)

    def test_inferencia_bloqueia_dados_insuficientes(self):
        with self.assertRaises(ValueError):
            prever(self.modelo, {})

    def test_temporal_sem_pacientes_compartilhados(self):
        d = coorte()
        d.loc[d.paciente_id.ge("FICTICIO_020"), "t0"] = "2026-01-01"
        d.loc[d.paciente_id.ge("FICTICIO_020"), "fim_acompanhamento"] = "2026-03-01"
        d = d.drop_duplicates(["paciente_id", "t0"])
        r = treinar(d, corte_temporal="2025-12-31")
        self.assertEqual(r["auditoria"]["pacientes_teste"], 20)


if __name__ == "__main__":
    unittest.main()
