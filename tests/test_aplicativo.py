"""Verifica escopo do CID e ciclo de vida do serviço local."""

import subprocess
import time
import unittest

from iniciar_app import (
    comando_servidor,
    encerrar_processo,
    porta_disponivel,
    servidor_pronto,
)
from src.paciente import Paciente, validar_paciente


class TestAplicativo(unittest.TestCase):
    def test_cid_exclusivo(self):
        self.assertEqual(validar_paciente(Paciente()).cid_codigo, "D57.0")
        with self.assertRaises(ValueError):
            validar_paciente(Paciente(cid_codigo="D57.1"))

    def test_servidor_inicia_e_encerra(self):
        porta = porta_disponivel()
        processo = subprocess.Popen(
            comando_servidor(porta),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            limite = time.monotonic() + 25
            while time.monotonic() < limite:
                if servidor_pronto(porta) or processo.poll() is not None:
                    break
                time.sleep(0.2)
            self.assertTrue(servidor_pronto(porta))
        finally:
            encerrar_processo(processo)
        self.assertIsNotNone(processo.poll())
        self.assertFalse(servidor_pronto(porta))


if __name__ == "__main__":
    unittest.main()
