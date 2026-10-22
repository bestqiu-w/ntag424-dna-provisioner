"""
NTAG 424 DNA - Modular & Fully Customizable Key Derivation Function (KDF) Engine
Allows users to configure every parameter:
1. Core Algorithm: HKDF-SHA256, AES-128-CMAC, HMAC-SHA256, FIXED_KEY
2. Salt Source: UID_STR (ASCII hex), UID_BYTES (7B binary), CUSTOM (arbitrary string), NONE
3. Info / Context Pattern: Arbitrary string with {UID}, {SLOT}, {SALT} placeholders
"""

import hashlib
import hmac
from typing import Union, Dict, Optional, Any
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

KDF_ALGORITHMS = [
    "HKDF-SHA256",
    "AES-128-CMAC",
    "HMAC-SHA256",
    "FIXED_KEY",
]


def aes_cmac(key: bytes, data: bytes) -> bytes:
    """Calculate AES-128 CMAC (16 bytes)."""
    c = CMAC(algorithms.AES(key), backend=default_backend())
    c.update(data)
    return c.finalize()


def derive_key_configurable(
    master_key: Union[bytes, str],
    uid: Union[bytes, str],
    key_no: int,
    algorithm: str = "HKDF-SHA256",
    salt_source: str = "UID_STR",
    custom_salt: str = "",
    info_pattern: str = "ntag424|{UID}|{SLOT}",
) -> bytes:
    """
    Derives a 16-byte AES-128 key based on user-configured KDF parameters.

    :param master_key: 16-byte Master Key (bytes or hex string)
    :param uid: 7-byte Card UID (bytes or hex string)
    :param key_no: Key slot number (0..4)
    :param algorithm: 'HKDF-SHA256', 'AES-128-CMAC', 'HMAC-SHA256', or 'FIXED_KEY'
    :param salt_source: 'UID_STR', 'UID_BYTES', 'CUSTOM', or 'NONE'
    :param custom_salt: Project salt string when salt_source is 'CUSTOM'
    :param info_pattern: Context template, supports {UID}, {SLOT}, {SALT} placeholders
    :return: 16-byte AES-128 key
    """
    if isinstance(master_key, str):
        master_key = bytes.fromhex(master_key.replace(" ", "").replace(":", ""))
    if isinstance(uid, str):
        uid = bytes.fromhex(uid.replace(" ", "").replace(":", ""))

    if len(master_key) != 16:
        raise ValueError(f"Master Key must be 16 bytes, got {len(master_key)}")
    if len(uid) != 7:
        raise ValueError(f"NTAG 424 DNA UID must be 7 bytes, got {len(uid)}")
    if not (0 <= key_no <= 4):
        raise ValueError(f"key_no must be between 0 and 4, got {key_no}")

    uid_hex = uid.hex().upper()

    # 1. Resolve Salt
    salt_src_upper = salt_source.strip().upper()
    if salt_src_upper in ("UID_STR", "UID_HEX", "UID"):
        salt_bytes: Optional[bytes] = uid_hex.encode("utf-8")
    elif salt_src_upper in ("UID_BYTES", "UID_BIN"):
        salt_bytes = uid
    elif salt_src_upper in ("CUSTOM", "SALT"):
        resolved_salt = custom_salt.replace("{UID}", uid_hex)
        salt_bytes = resolved_salt.encode("utf-8")
    elif salt_src_upper in ("NONE", "EMPTY"):
        salt_bytes = None
    else:
        # Fallback to custom salt if non-empty, otherwise UID string
        salt_bytes = custom_salt.encode("utf-8") if custom_salt else uid_hex.encode("utf-8")

    # 2. Resolve Info / Context String
    pattern = info_pattern.strip() if info_pattern else "ntag424|{UID}|{SLOT}"
    info_str = (
        pattern.replace("{UID}", uid_hex)
        .replace("{SLOT}", str(key_no))
        .replace("{KEY_NO}", str(key_no))
        .replace("{SALT}", custom_salt)
    )
    info_bytes = info_str.encode("utf-8")

    # 3. Execute Core Derivation Algorithm
    algo_norm = algorithm.strip().upper().replace(" ", "_").replace("-", "_")

    if "FIXED" in algo_norm:
        # Static key with key_no modifier
        return master_key[:-1] + bytes([master_key[-1] ^ key_no])

    elif "CMAC" in algo_norm:
        # AES-128-CMAC derivation
        # If standard NXP pattern, use 0x01 || key_no || uid || salt (16 bytes)
        if pattern == "NXP" or len(info_bytes) != 16:
            div_header = bytes([0x01, key_no]) + uid  # 9 bytes
            remaining = 16 - len(div_header)  # 7 bytes
            salt_part = (salt_bytes or b"")[:remaining].ljust(remaining, b"\x00")
            div_input = div_header + salt_part
        else:
            div_input = info_bytes[:16].ljust(16, b"\x00")
        return aes_cmac(master_key, div_input)

    elif "HMAC" in algo_norm:
        # HMAC-SHA256 truncated to 16 bytes: HMAC(master_key, info_bytes + salt_bytes)
        data = info_bytes + (salt_bytes if salt_bytes else b"")
        digest = hmac.new(master_key, data, hashlib.sha256).digest()
        return digest[:16]

    else:
        # Default: HKDF-SHA256 (RFC 5869)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=salt_bytes,
            info=info_bytes,
            backend=default_backend(),
        )
        return hkdf.derive(master_key)


def derive_key(
    master_key: Union[bytes, str],
    uid: Union[bytes, str],
    key_no: int,
    salt: Union[bytes, str] = b"PATROL_SALT_2026",
    algorithm: str = "HKDF-SHA256",
    kdf_config: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Unified entry point for key derivation. Compatible with legacy calls and new modular configs.
    """
    if kdf_config:
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm=kdf_config.get("algorithm", algorithm),
            salt_source=kdf_config.get("salt_source", "UID_STR"),
            custom_salt=kdf_config.get("custom_salt", str(salt)),
            info_pattern=kdf_config.get("info_pattern", "ntag424|{UID}|{SLOT}"),
        )

    # Legacy signature mapping
    algo_norm = algorithm.strip().upper().replace(" ", "_").replace("-", "_")
    if "UID_SLOT" in algo_norm:
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm="HKDF-SHA256",
            salt_source="UID_STR",
            info_pattern="ntag424|{UID}|{SLOT}",
        )
    elif "CMAC" in algo_norm:
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm="AES-128-CMAC",
            salt_source="CUSTOM",
            custom_salt=salt.decode("utf-8") if isinstance(salt, bytes) else str(salt),
        )
    elif "HMAC" in algo_norm:
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm="HMAC-SHA256",
            salt_source="CUSTOM",
            custom_salt=salt.decode("utf-8") if isinstance(salt, bytes) else str(salt),
            info_pattern=f"slot_{key_no}|{{UID}}",
        )
    elif "FIXED" in algo_norm:
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm="FIXED_KEY",
        )
    else:
        # Default HKDF
        return derive_key_configurable(
            master_key=master_key,
            uid=uid,
            key_no=key_no,
            algorithm="HKDF-SHA256",
            salt_source="UID_STR",
            info_pattern="ntag424|{UID}|{SLOT}",
        )


def derive_all_keys(
    master_key: Union[bytes, str],
    uid: Union[bytes, str],
    salt: Union[bytes, str] = b"PATROL_SALT_2026",
    algorithm: str = "HKDF-SHA256",
    kdf_config: Optional[Dict[str, Any]] = None,
) -> Dict[int, bytes]:
    """
    Derives all 5 keys (Key 0 ~ Key 4) for the given UID using the specified KDF configuration.
    """
    return {
        i: derive_key(master_key, uid, i, salt=salt, algorithm=algorithm, kdf_config=kdf_config)
        for i in range(5)
    }
