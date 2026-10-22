"""
Standalone NTAG 424 DNA protocol engine test.
Directly implements EV2 First Auth, ChangeKey (with CRC32NK and XOR), and ChangeFileSettings.
"""

import binascii
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.backends import default_backend


def aes_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def aes_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


def aes_cmac(key: bytes, data: bytes) -> bytes:
    c = CMAC(algorithms.AES(key), backend=default_backend())
    c.update(data)
    return c.finalize()


def pad_iso7816(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + b"\x80" + (b"\x00" * (pad_len - 1))


def crc32nk(data: bytes) -> bytes:
    # CRC32 Jam (IEEE 802.3 with inverted final XOR) in Little Endian
    crc = binascii.crc32(data) & 0xFFFFFFFF
    jam = crc ^ 0xFFFFFFFF
    return struct.pack("<I", jam)



def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))
