"""
Test suite for Recipe Export and Import.
"""
import os
import json
import tempfile
from utils.config import DEFAULT_CONFIG, load_config, save_config

def test_recipe_roundtrip():
    # 1. Prepare sample recipe
    custom_recipe = {
        "recipe_name": "Test_Custom_Patrol",
        "version": "1.0",
        "master_key": "FEDCBA9876543210FEDCBA9876543210",
        "kdf_algorithm": "HMAC-SHA256",
        "kdf_salt_source": "CUSTOM",
        "kdf_custom_salt": "TEST_SALT_XYZ",
        "kdf_info_pattern": "test|{UID}|{SLOT}",
        "sdm_mac_key": 2,
        "key_version": 5,
        "url_template": "https://test.domain.com/check?u={UID}&c={CTR}&m={CMAC}",
        "auto_buzzer": False,
        "file01_enabled": True,
        "file01_comm_mode": "0x00",
        "file01_read": "0xE",
        "file01_write": "0xF",
        "file01_change": "0x0",
        "file02_sdm": True,
        "file02_comm_mode": "0x00",
        "file02_read": "0xE",
        "file02_write": "0x0",
        "file02_change": "0x0",
        "file02_meta_key": "0x1",
        "file02_ctr_ret_key": "0xF",
        "enable_uid_mirror": True,
        "enable_ctr_mirror": False,
        "file03_enabled": True,
        "file03_comm_mode": "0x01",
        "file03_read": "0x2",
        "file03_write": "0x0",
        "file03_change": "0x0",
    }

    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        json.dump(custom_recipe, tf, indent=2)
        tmp_path = tf.name

    try:
        # 2. Read back and merge into a clean config dict
        with open(tmp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = DEFAULT_CONFIG.copy()
        for k in DEFAULT_CONFIG.keys():
            if k in data:
                config[k] = data[k]

        assert config["master_key"] == "FEDCBA9876543210FEDCBA9876543210"
        assert config["kdf_algorithm"] == "HMAC-SHA256"
        assert config["kdf_custom_salt"] == "TEST_SALT_XYZ"
        assert config["kdf_info_pattern"] == "test|{UID}|{SLOT}"
        assert config["sdm_mac_key"] == 2
        assert config["file01_enabled"] is True
        assert config["file01_comm_mode"] == "0x00"
        assert config["file01_write"] == "0xF"
        assert config["file01_change"] == "0x0"
        assert config["file02_change"] == "0x0"
        assert config["file02_ctr_ret_key"] == "0xF"
        assert config["file03_comm_mode"] == "0x01"
        assert config["file03_change"] == "0x0"
        assert config["enable_ctr_mirror"] is False
        print("✓ Recipe import/export parsing validation passed!")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    test_recipe_roundtrip()
    print("All recipe tests passed successfully!")
