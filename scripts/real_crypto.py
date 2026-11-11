"""Cifra las posiciones reales para el panel publico (openssl, AES-256-CBC, PBKDF2).

El formato es el de 'openssl enc' con cabecera Salted__, para que el panel lo descifre en el navegador
con WebCrypto. La clave es la misma frase de paso que el estado (STATE_KEY).
"""
import os
import subprocess

PBKDF2_ITER = 200000


def run_openssl(args, data, passphrase):
    env = {**os.environ, "REAL_CRYPT_PASS": passphrase}
    result = subprocess.run(
        ["openssl", "enc", *args, "-pbkdf2", "-iter", str(PBKDF2_ITER), "-md", "sha256",
         "-pass", "env:REAL_CRYPT_PASS"],
        input=data, capture_output=True, check=True, env=env,
    )
    return result.stdout


def encrypt(plaintext, passphrase):
    return run_openssl(["-aes-256-cbc", "-salt"], plaintext, passphrase)


def decrypt(ciphertext, passphrase):
    return run_openssl(["-d", "-aes-256-cbc"], ciphertext, passphrase)
