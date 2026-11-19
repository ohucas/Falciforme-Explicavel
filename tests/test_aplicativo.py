"""Verifica o escopo do CID."""

import unittest

from src.paciente import Paciente, validar_paciente


class TestAplicativo(unittest.TestCase):
    def test_cid_exclusivo(self):
        self.assertEqual(validar_paciente(Paciente()).cid_codigo, "D57.0")
        with self.assertRaises(ValueError):
            validar_paciente(Paciente(cid_codigo="D57.1"))
