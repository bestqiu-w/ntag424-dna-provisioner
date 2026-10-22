"""
Unit tests for KDF, SDM builder, and FileSettings generation.
"""

from core.kdf import derive_key, derive_all_keys, KDF_ALGORITHMS
from core.sdm_builder import build_sdm_ndef


def test_kdf():
    master_key = "00112233445566778899AABBCCDDEEFF"
    uid = "04A1B2C3D4E5F6"
    salt = "PATROL_TEST"

    for algo in KDF_ALGORITHMS:
        keys = derive_all_keys(master_key, uid, salt, algorithm=algo)
        assert len(keys) == 5
        for k_no, key in keys.items():
            assert len(key) == 16
        print(f"[{algo}] Key 0: {keys[0].hex().upper()}, Key 2: {keys[2].hex().upper()}")

    print("All KDF algorithm tests passed!")


def test_sdm_builder():
    url = "https://patrol.example.com/v?u={UID}&c={CTR}&m={CMAC}"
    cfg = build_sdm_ndef(url)

    print(f"URL Template: {cfg.url_template}")
    print(f"UID Offset: {cfg.uid_offset}")
    print(f"CTR Offset: {cfg.ctr_offset}")
    print(f"MAC Offset: {cfg.mac_offset}")
    print(f"MAC Input Offset: {cfg.mac_input_offset}")
    print(f"Raw NDEF bytes ({len(cfg.ndef_record_bytes)} bytes): {cfg.ndef_record_bytes.hex()}")

    # Check offsets against the raw bytes
    raw_bytes = cfg.ndef_record_bytes
    # UID placeholder was 14 '0's
    extracted_uid_placeholder = raw_bytes[cfg.uid_offset : cfg.uid_offset + 14]
    assert extracted_uid_placeholder == b"0" * 14

    # CTR placeholder was 6 '0's
    extracted_ctr_placeholder = raw_bytes[cfg.ctr_offset : cfg.ctr_offset + 6]
    assert extracted_ctr_placeholder == b"0" * 6

    # CMAC placeholder was 16 '0's
    extracted_cmac_placeholder = raw_bytes[cfg.mac_offset : cfg.mac_offset + 16]
    assert extracted_cmac_placeholder == b"0" * 16

    print("SDM Builder offset test passed!")


if __name__ == "__main__":
    test_kdf()
    test_sdm_builder()
    print("All core tests passed successfully!")
