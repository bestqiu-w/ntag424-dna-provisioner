"""
Local configuration persistence for NTAG 424 DNA batch tool.
"""

import json
import os
import secrets
from typing import Dict, Any

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def generate_random_recipe_name() -> str:
    """Generate a random short recipe name like Recipe_A8F2."""
    suffix = secrets.token_hex(2).upper()
    return f"Recipe_{suffix}"


DEFAULT_CONFIG = {
    "recipe_name": "Default_Patrol",
    "master_key": "00112233445566778899AABBCCDDEEFF",
    "factory_key": "00000000000000000000000000000000",
    "url_template": "https://patrol.example.com/v?u={UID}&c={CTR}&m={CMAC}",
    "auto_buzzer": True,
    # Android Application Record (AAR) Settings
    "enable_aar": False,
    "aar_package_name": "com.example.patrol",
    # Modular KDF Engine Settings
    "kdf_algorithm": "HKDF-SHA256",
    "kdf_salt_source": "UID_STR",  # UID_STR, UID_BYTES, CUSTOM, NONE
    "kdf_custom_salt": "PATROL_SYSTEM_2026",
    "kdf_info_pattern": "ntag424|{UID}|{SLOT}",
    "sdm_mac_key": 3,
    "key_version": 1,
    # File 01 Settings
    "file01_enabled": False,
    "file01_comm_mode": "0x00",
    "file01_read": "0xE",
    "file01_write": "0x0",
    "file01_change": "0x0",
    # File 02 Settings
    "file02_sdm": True,
    "file02_comm_mode": "0x00",
    "file02_read": "0xE",
    "file02_write": "0x0",
    "file02_change": "0x0",
    "file02_meta_key": "0xE",
    "file02_ctr_ret_key": "0xF",
    "enable_uid_mirror": True,
    "enable_ctr_mirror": True,
    # File 03 Settings
    "file03_enabled": False,
    "file03_comm_mode": "0x03",
    "file03_read": "0x3",
    "file03_write": "0x0",
    "file03_change": "0x0",
}


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG, path)
        return DEFAULT_CONFIG.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults in case of missing keys
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any], path: str = DEFAULT_CONFIG_PATH) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def generate_random_key() -> str:
    """Generate a random 16-byte AES-128 hex string."""
    return secrets.token_hex(16).upper()
