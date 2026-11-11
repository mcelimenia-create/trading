"""Tests del cifrado de posiciones reales para el panel."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import real_crypto  # noqa: E402


class RealCryptoTest(unittest.TestCase):
    def test_roundtrip_returns_the_same_bytes(self):
        data = b'{"open": [{"symbol": "TSLA"}]}'
        blob = real_crypto.encrypt(data, "frase-de-prueba")
        self.assertEqual(real_crypto.decrypt(blob, "frase-de-prueba"), data)

    def test_output_is_openssl_format_and_not_plain_text(self):
        blob = real_crypto.encrypt(b'{"open": []}', "frase-de-prueba")
        self.assertTrue(blob.startswith(b"Salted__"))
        self.assertNotIn(b'"open"', blob)

    def test_wrong_passphrase_fails(self):
        blob = real_crypto.encrypt(b"hola", "buena")
        with self.assertRaises(Exception):
            real_crypto.decrypt(blob, "mala")


if __name__ == "__main__":
    unittest.main()
