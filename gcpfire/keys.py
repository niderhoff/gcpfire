"""generate key pair"""

import os
from typing import Optional, Tuple

from cryptography.hazmat.backends import default_backend as crypto_default_backend
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gcpfire.logger import logger


def generate_keypair(username: str = "gcpfire") -> Tuple[bytes, bytes]:
    logger.debug("Generating key pair.")
    key = rsa.generate_private_key(
        backend=crypto_default_backend(), public_exponent=65537, key_size=2048  # type: ignore
    )
    private_key = key.private_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PrivateFormat.TraditionalOpenSSL,
        crypto_serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        crypto_serialization.Encoding.OpenSSH, crypto_serialization.PublicFormat.OpenSSH
    )
    if username is not None:
        public_key = (public_key.decode() + " " + username).encode()
    return (private_key, public_key)


def write_pubkey(key: bytes, name: Optional[str] = None, outpath: str = os.getcwd()) -> str:
    pubkey_name = os.path.join(outpath, name + ".key" if name is not None else "public.key")
    with open(pubkey_name, "wb") as pubkey_file:
        pubkey_file.write(key)
    return pubkey_name


def write_privatekey(key: bytes, name: Optional[str] = None, outpath: str = os.getcwd()) -> str:
    pkey_name = os.path.join(outpath, name + "_private.key" if name is not None else "private.key")
    with open(pkey_name, "wb") as pkey_file:  # TODO: os.makedirs
        os.chmod(pkey_name, 0o600)
        pkey_file.write(key)
    return pkey_name


def delete_key_file(file_path: str) -> None:
    if file_path is not None and os.path.exists(file_path):
        logger.debug("Deleting local key file.")
        os.remove(file_path)
