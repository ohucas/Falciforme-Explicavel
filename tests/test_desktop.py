"""Contratos do fluxo nativo com dados fictícios, sem escrever dados pessoais."""
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from src.desktop.janela import Janela

class TestDesktop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.janela=Janela()
        self.janela.abrir_demo()
        self.janela.revisado.setChecked(True)
        self.janela.analisar()

    def tearDown(self):
        self.janela.close()

    def test_tres_coletas_sao_comparadas(self):
        self.assertEqual(len(self.janela.exames),3)
        self.assertTrue(self.janela.exportar.isEnabled())

    def test_edicao_invalida_analise(self):
        self.janela.tabela.item(0,4).setText('8.5')
        self.assertIsNone(self.janela.exames)
        self.assertFalse(self.janela.exportar.isEnabled())

    def test_pdf_e_limpeza(self):
        with TemporaryDirectory() as pasta:
            destino=str(Path(pasta)/'teste.pdf')
            with patch('src.desktop.janela.QFileDialog.getSaveFileName',return_value=(destino,'PDF')):
                self.janela.salvar_pdf()
            self.assertTrue(Path(destino).read_bytes().startswith(b'%PDF'))
        self.janela.limpar_sessao()
        self.assertEqual(self.janela.tabela.rowCount(),0)
        self.assertIsNone(self.janela.exames)
