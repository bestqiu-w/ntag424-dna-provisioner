"""
NTAG 424 DNA - Server-Side Verification Reference Implementation
Demonstrates how the backend validates dynamic SUN URLs without querying a key database:
1. Parse UID and Counter from the scanned URL
2. Derive Key 3 in memory using HKDF-SHA256 (ntag424|UID|slot)
3. Compute expected dynamic AES-CMAC and compare with the URL MAC
"""

import struct
from urllib.parse import urlparse, parse_qs
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


def aes_cmac(key: bytes, data: bytes) -> bytes:
    """Computes AES-128 CMAC (16 bytes)."""
    c = CMAC(algorithms.AES(key), backend=default_backend())
    c.update(data)
    return c.finalize()


def derive_key3_hkdf_slot(root_key: bytes, uid_hex: str) -> bytes:
    """
    Derives Key 3 using HKDF-SHA256 with info="ntag424|{uid_hex}|3".
    """
    uid_upper = uid_hex.upper()
    info = f"ntag424|{uid_upper}|3".encode("utf-8")
    salt = uid_upper.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        info=info,
        backend=default_backend(),
    )
    return hkdf.derive(root_key)


def verify_sun_url(root_key: bytes, scanned_url: str) -> bool:
    """
    Validates an incoming scanned NTAG 424 DNA patrol URL.
    Returns True if authentic, False otherwise.
    """
    parsed = urlparse(scanned_url)
    qs = parse_qs(parsed.query)

    uid_param = qs.get("u", qs.get("uid", [None]))[0]
    ctr_param = qs.get("c", qs.get("ctr", [None]))[0]
    mac_param = qs.get("m", qs.get("cmac", [None]))[0]

    if not uid_param or not ctr_param or not mac_param:
        return False

    # 1. Derive Key 3 in memory
    key3 = derive_key3_hkdf_slot(root_key, uid_param)

    # 2. Derive Session MAC Key (KSesAuthMac) according to NTAG 424 DNA AN12196
    # SV = 3C C3 00 01 00 80 || SDMReadCtr (3 bytes LE) || 00*7
    ctr_val = int(ctr_param, 16) if len(ctr_param) == 6 else int(ctr_param)
    ctr_bytes_le = struct.pack("<I", ctr_val)[:3]
    sv = b"\x3C\xC3\x00\x01\x00\x80" + ctr_bytes_le + (b"\x00" * 7)
    k_ses_mac = aes_cmac(key3, sv)

    # 3. Compute CMAC over the ASCII data preceding the MAC placeholder
    # The MAC input is the URL substring from 'u=' up to '&m='
    mac_pos = scanned_url.find("&m=")
    if mac_pos < 0:
        mac_pos = scanned_url.find("&cmac=")
    u_pos = scanned_url.find("u=")
    if u_pos < 0:
        u_pos = scanned_url.find("uid=")

    mac_input_data = scanned_url[u_pos : mac_pos + 3].encode("ascii")

    full_cmac = aes_cmac(k_ses_mac, mac_input_data)
    expected_mac = full_cmac[1::2].hex().upper()

    return expected_mac == mac_param.upper()
