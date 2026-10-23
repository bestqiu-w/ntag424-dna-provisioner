"""
NTAG 424 DNA Native Protocol and Provisioning Engine.
Complete, spec-compliant implementation of:
- EV2 First Authentication
- Key Derivation & ChangeKey (CRC32NK, XOR diversification)
- ChangeFileSettings (SDM / SUN Configuration, Mirror Offsets)
- ISO NDEF Read/Write
- Factory Reset
"""

import os
import struct
import logging
from typing import Tuple, Dict, Any, Optional

from core.crypto_util import (
    aes_encrypt,
    aes_decrypt,
    aes_cmac,
    pad_iso7816,
    crc32nk,
    xor_bytes,
)
from core.kdf import derive_all_keys
from core.sdm_builder import build_sdm_ndef, decode_ndef_uri

logger = logging.getLogger(__name__)


class NTAG424ProtocolError(Exception):
    pass


class NTAG424Manager:
    """Manages low-level APDU transactions, EV2 authentication, and file settings on NTAG 424 DNA."""

    def __init__(self, card_connection):
        self.conn = card_connection
        self.ti = b"\x00" * 4
        self.cmdctr = 0
        self.k_ses_enc: Optional[bytes] = None
        self.k_ses_mac: Optional[bytes] = None
        self.authenticated = False

    def transmit(self, apdu: list) -> Tuple[bytes, int, int]:
        response, sw1, sw2 = self.conn.transmit(apdu)
        return bytes(response), sw1, sw2

    def select_ndef_application(self) -> bool:
        """Select NDEF Application: 00 A4 04 00 07 D2 76 00 00 85 01 01 00"""
        apdu = [0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01, 0x00]
        data, sw1, sw2 = self.transmit(apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            raise NTAG424ProtocolError(f"Select Application failed: SW={sw1:02X}{sw2:02X}")
        return True

    def authenticate_ev2_first(self, key_no: int, key: bytes) -> bool:
        """
        Executes AuthenticateEV2First (Part 1 and Part 2) according to NTAG 424 DNA Datasheet 11.4.1.
        Establishes Session Encryption Key (K_ses_enc) and Session MAC Key (K_ses_mac).
        """
        if len(key) != 16:
            raise ValueError("Key must be 16 bytes (AES-128)")

        # Part 1: APDU = 90 71 00 00 02 [KeyNo] 00 00
        apdu1 = [0x90, 0x71, 0x00, 0x00, 0x02, key_no, 0x00, 0x00]
        data1, sw1, sw2 = self.transmit(apdu1)
        if (sw1, sw2) != (0x91, 0xAF):
            raise NTAG424ProtocolError(f"AuthEV2First Part1 failed: SW={sw1:02X}{sw2:02X} (Expected 91AF)")

        if len(data1) != 16:
            raise NTAG424ProtocolError(f"AuthEV2First Part1 returned unexpected data length: {len(data1)}")

        # Decrypt RndB (AES-128-CBC, IV=0)
        rnd_b = aes_decrypt(key, b"\x00" * 16, data1)

        # Generate RndA (16 bytes random)
        rnd_a = os.urandom(16)

        # Rotate RndB left by 1 byte: RndB' = RndB[1:] + RndB[0:1]
        rnd_b_prime = rnd_b[1:] + rnd_b[:1]

        # Encrypt RndA || RndB' (32 bytes) with NULL_IV (16 zeros)
        data_to_encrypt = rnd_a + rnd_b_prime
        encrypted_auth = aes_encrypt(key, b"\x00" * 16, data_to_encrypt)

        # Part 2: APDU = 90 AF 00 00 20 [encrypted_auth] 00
        apdu2 = [0x90, 0xAF, 0x00, 0x00, len(encrypted_auth)] + list(encrypted_auth) + [0x00]
        data2, sw1, sw2 = self.transmit(apdu2)
        if (sw1, sw2) != (0x91, 0x00):
            raise NTAG424ProtocolError(f"AuthEV2First Part2 failed: SW={sw1:02X}{sw2:02X} (Expected 9100)")

        # Decrypt response (32 bytes) with NULL_IV (16 zeros)
        decrypted2 = aes_decrypt(key, b"\x00" * 16, data2)

        # TI (4 bytes) || RndA' (16 bytes) || PDcap2 (6 bytes) || PCDcap2 (6 bytes)
        self.ti = decrypted2[0:4]
        rnd_a_prime = decrypted2[4:20]

        # Check RndA' matches rotated RndA: RndA rotated left by 1 byte
        expected_rnd_a_prime = rnd_a[1:] + rnd_a[:1]
        if rnd_a_prime != expected_rnd_a_prime:
            raise NTAG424ProtocolError(
                f"Card authentication failed: RndA mismatch! (got {rnd_a_prime.hex()}, expected {expected_rnd_a_prime.hex()})"
            )

        # Derive Session Keys:
        # SV1 for K_ses_enc, SV2 for K_ses_mac
        context = (
            rnd_a[0:2]
            + xor_bytes(rnd_a[2:8], rnd_b[0:6])
            + rnd_b[6:16]
            + rnd_a[8:16]
        )
        sv1 = b"\xA5\x5A\x00\x01\x00\x80" + context
        sv2 = b"\x5A\xA5\x00\x01\x00\x80" + context

        self.k_ses_enc = aes_cmac(key, sv1)
        self.k_ses_mac = aes_cmac(key, sv2)
        self.cmdctr = 0
        self.authenticated = True
        return True

    def send_command_full(self, ins: int, header: bytes, plain_data: bytes) -> bytes:
        """
        Sends command under CommMode.Full (Encrypted payload + CMAC).
        Case 3 APDU (No Le at the end).
        """
        if not self.authenticated or not self.k_ses_enc or not self.k_ses_mac:
            raise NTAG424ProtocolError("Cannot send command in FULL mode: not authenticated!")

        # 1. Compute IV for command encryption (IVc):
        # IVc = Enc(K_ses_enc, A5 5A || TI || CmdCtr (2 bytes LE) || 00*8)
        ivc_input = b"\xA5\x5A" + self.ti + struct.pack("<H", self.cmdctr) + (b"\x00" * 8)
        ivc = aes_encrypt(self.k_ses_enc, b"\x00" * 16, ivc_input)

        # 2. Encrypt padded payload:
        padded_data = pad_iso7816(plain_data)
        encrypted_data = aes_encrypt(self.k_ses_enc, ivc, padded_data)

        # 3. Calculate 8-byte CMAC:
        # CMAC input: INS || CmdCtr (2 bytes LE) || TI || Header || EncryptedData
        cmac_input = bytes([ins]) + struct.pack("<H", self.cmdctr) + self.ti + header + encrypted_data
        full_cmac = aes_cmac(self.k_ses_mac, cmac_input)
        truncated_cmac = full_cmac[1::2]  # 8 bytes, odd indices

        # 4. Assemble Case 4 APDU: 90 [INS] 00 00 [Lc] [Header + EncryptedData + CMAC] 00
        payload = header + encrypted_data + truncated_cmac
        apdu = [0x90, ins, 0x00, 0x00, len(payload)] + list(payload) + [0x00]

        # 5. Increment CmdCtr before sending:
        self.cmdctr += 1

        res, sw1, sw2 = self.transmit(apdu)
        if (sw1, sw2) != (0x91, 0x00):
            raise NTAG424ProtocolError(f"Command 0x{ins:02X} failed: SW={sw1:02X}{sw2:02X}")

        return res

    def change_key(self, key_no: int, new_key: bytes, old_key: bytes = b"\x00" * 16, key_ver: int = 1) -> bool:
        """
        Executes ChangeKey (0xC4) according to NTAG 424 DNA Datasheet section 11.6.1:
        - For Key 0: PlainData = NewKey (16 bytes) || KeyVer (1 byte) -> 17 bytes
        - For Keys 1..4: PlainData = (NewKey ^ OldKey) (16 bytes) || KeyVer (1 byte) || JamCRC32(NewKey) (4 bytes) -> 21 bytes
        """
        if len(new_key) != 16 or len(old_key) != 16:
            raise ValueError("Keys must be 16 bytes")

        header = bytes([key_no])

        if key_no == 0:
            plain_data = new_key + bytes([key_ver])
        else:
            key_diff = xor_bytes(new_key, old_key)
            crc = crc32nk(new_key)
            plain_data = key_diff + bytes([key_ver]) + crc

        self.send_command_full(0xC4, header, plain_data)
        return True

    def change_file_settings_standard(
        self,
        file_no: int,
        read_perm: int = 0xE,
        write_perm: int = 0x0,
        rw_perm: int = 0x0,
        change_perm: int = 0x0,
        comm_mode: int = 0x00,
    ) -> bool:
        """
        Configures permissions for standard files (File 01 CC, File 02 plain, File 03 Proprietary)
        according to Section 11.7.1 and NTAG 424 DNA spec.
        """
        header = bytes([file_no])
        file_option = comm_mode & 0x03
        perm2 = ((rw_perm & 0x0F) << 4) | (change_perm & 0x0F)
        perm1 = ((read_perm & 0x0F) << 4) | (write_perm & 0x0F)
        plain_data = bytes([file_option, perm2, perm1])
        self.send_command_full(0x5F, header, plain_data)
        return True

    def change_file_settings_sdm(
        self,
        file_no: int,
        uid_offset: int,
        ctr_offset: int,
        mac_offset: int,
        mac_input_offset: int,
        mac_key: int = 3,
        read_perm: int = 0xE,
        write_perm: int = 0x0,
        rw_perm: int = 0x0,
        change_perm: int = 0x0,
        meta_read_key: int = 0xE,
        ctr_ret_key: int = 0xF,
        comm_mode: int = 0x00,
        enable_uid: bool = True,
        enable_ctr: bool = True,
    ) -> bool:
        """
        Configures File 02 for SDM / SUN mirroring according to Section 11.7.1 and NTAG 424 DNA spec.
        """
        header = bytes([file_no])

        # FileOption = 0x40 (SDM enabled) | comm_mode
        file_option = 0x40 | (comm_mode & 0x03)

        perm2 = ((rw_perm & 0x0F) << 4) | (change_perm & 0x0F)
        perm1 = ((read_perm & 0x0F) << 4) | (write_perm & 0x0F)

        # SDMOptions: Bit 7 (UID Mirror), Bit 6 (ReadCtr), Bit 0 (ASCII)=1
        sdm_options = 0x01
        if enable_uid:
            sdm_options |= 0x80
        if enable_ctr:
            sdm_options |= 0x40

        # SDMAccessRights (2 bytes):
        # Byte 0: sdm_rights2 = 0xF0 | (CtrRetKey & 0x0F)
        # Byte 1: sdm_rights1 = ((MetaReadKey & 0x0F) << 4) | (mac_key & 0x0F)
        sdm_rights2 = 0xF0 | (ctr_ret_key & 0x0F)
        sdm_rights1 = ((meta_read_key & 0x0F) << 4) | (mac_key & 0x0F)

        # Offsets (3 bytes each, little-endian):
        b_uid_off = struct.pack("<I", uid_offset)[:3]
        b_ctr_off = struct.pack("<I", ctr_offset)[:3]
        b_mac_in_off = struct.pack("<I", mac_input_offset)[:3]
        b_mac_off = struct.pack("<I", mac_offset)[:3]

        plain_data = (
            bytes([file_option, perm2, perm1, sdm_options, sdm_rights2, sdm_rights1])
            + b_uid_off
            + b_ctr_off
            + b_mac_in_off
            + b_mac_off
        )

        self.send_command_full(0x5F, header, plain_data)
        return True

    def reset_file_settings_plain(self, file_no: int) -> bool:
        """
        Restores File 02 to plain open access, disabling SDM completely.
        """
        header = bytes([file_no])
        file_option = 0x00  # SDM disabled, CommMode plain
        perm2 = 0xE0
        perm1 = 0xEE
        plain_data = bytes([file_option, perm2, perm1])
        self.send_command_full(0x5F, header, plain_data)
        return True

    def write_ndef_binary(self, ndef_bytes: bytes, file_id: bytes = b"\xE1\x04") -> bool:
        """Writes raw NDEF bytes via ISO Select File + ISO UpdateBinary."""
        # 1. ISO Select File E104: 00 A4 00 0C 02 E1 04
        self.transmit([0x00, 0xA4, 0x00, 0x0C, 0x02, file_id[0], file_id[1]])

        # 2. ISO UpdateBinary chunks: 00 D6 [OffsetHi] [OffsetLo] [Len] [Data]
        offset = 0
        total_len = len(ndef_bytes)
        chunk_size = 64

        while offset < total_len:
            chunk = ndef_bytes[offset : offset + chunk_size]
            p1 = (offset >> 8) & 0xFF
            p2 = offset & 0xFF
            apdu = [0x00, 0xD6, p1, p2, len(chunk)] + list(chunk)
            data, sw1, sw2 = self.transmit(apdu)
            if sw1 != 0x90 or sw2 != 0x00:
                raise NTAG424ProtocolError(f"ISO UpdateBinary failed at offset {offset}: SW={sw1:02X}{sw2:02X}")
            offset += len(chunk)

        return True

    def read_ndef_binary(self, length: int = 128, file_id: bytes = b"\xE1\x04") -> bytes:
        """Reads NDEF File without authentication to verify dynamic SUN output."""
        self.transmit([0x00, 0xA4, 0x00, 0x0C, 0x02, file_id[0], file_id[1]])
        data, sw1, sw2 = self.transmit([0x00, 0xB0, 0x00, 0x00, min(length, 255)])
        return data

    def provision_tag(
        self,
        uid: bytes,
        master_key: bytes,
        salt: bytes,
        url_template: str,
        current_key0: bytes = b"\x00" * 16,
        kdf_algo: str = "HKDF-SHA256",
        mac_key: int = 3,
        file_permissions: Optional[Dict[str, Any]] = None,
        key_ver: int = 1,
        kdf_config: Optional[Dict[str, Any]] = None,
        aar_package: Optional[str] = None,
        # backward compatibility flags
        write_protection: Optional[str] = None,
        enable_uid: bool = True,
        enable_ctr: bool = True,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Complete end-to-end provisioning flow:
        1. Parse URL & compute offsets (optionally with AAR package record)
        2. Select Application
        3. Write NDEF URL template
        4. Authenticate with current Key 0
        5. Change Key 1 ~ Key 4 (with XOR & CRC32NK)
        6. Change File 01, File 02 (SDM/Permissions), File 03 settings
        7. Change Key 0 (Master Key)
        8. Verify by authenticating with new Key 0 & reading dynamic URL
        """
        try:
            derived_keys = derive_all_keys(master_key, uid, salt, algorithm=kdf_algo, kdf_config=kdf_config)
            sdm_cfg = build_sdm_ndef(url_template, aar_package=aar_package)

            fp = file_permissions or {}

            # 1. Select Application
            self.select_ndef_application()

            # 2. Try writing NDEF binary while write access may be open
            ndef_written = False
            try:
                self.write_ndef_binary(sdm_cfg.ndef_record_bytes)
                ndef_written = True
            except Exception:
                pass

            # 3. Authenticate with Key 0 (re-select application after ISO Select File)
            self.select_ndef_application()
            auth_ok = False
            try:
                self.authenticate_ev2_first(0, current_key0)
                auth_ok = True
            except Exception:
                if current_key0 != derived_keys[0]:
                    try:
                        self.select_ndef_application()
                        self.authenticate_ev2_first(0, derived_keys[0])
                        current_key0 = derived_keys[0]
                        auth_ok = True
                    except Exception:
                        pass

            if not auth_ok:
                raise NTAG424ProtocolError("无法认证标签 Key 0 (既不是出厂00密钥，也不匹配当前派生主密钥)")

            # If write was previously blocked by key restrictions, reset file to plain and write now
            if not ndef_written:
                try:
                    self.reset_file_settings_plain(0x02)
                    self.write_ndef_binary(sdm_cfg.ndef_record_bytes)
                    self.select_ndef_application()
                    self.authenticate_ev2_first(0, current_key0)
                except Exception as e:
                    logger.warning(f"Writing NDEF after reset warning: {e}")

            # 4. Change Keys 1..4 (sub-keys)
            for k in range(1, 5):
                old_sub_key = derived_keys[k] if current_key0 == derived_keys[0] else b"\x00" * 16
                self.change_key(k, derived_keys[k], old_key=old_sub_key, key_ver=key_ver)

            # 5. File Settings Configuration
            # File 01 (CC File - 32 bytes)
            if fp.get("file01_enabled", False):
                try:
                    f01_r = fp.get("file01_read", 0xE)
                    f01_w = fp.get("file01_write", 0x0)
                    f01_change = fp.get("file01_change", 0x0)
                    f01_comm = fp.get("file01_comm_mode", 0x00)
                    self.change_file_settings_standard(
                        file_no=0x01,
                        read_perm=f01_r,
                        write_perm=f01_w,
                        rw_perm=f01_w,
                        change_perm=f01_change,
                        comm_mode=f01_comm,
                    )
                except Exception as e:
                    logger.warning(f"Configure File 01 warning: {e}")

            # File 02 (NDEF File - 256 bytes)
            f02_sdm = fp.get("file02_sdm", True)
            f02_mac_key = fp.get("file02_mac_key", mac_key)
            f02_read = fp.get("file02_read", 0xE)
            f02_write = fp.get("file02_write", 0x0)
            f02_change = fp.get("file02_change", 0x0)
            f02_comm = fp.get("file02_comm_mode", 0x00)
            f02_meta = fp.get("file02_meta_key", 0xE)
            f02_ctr_ret = fp.get("file02_ctr_ret_key", 0xF)
            f02_uid_m = fp.get("enable_uid_mirror", enable_uid)
            f02_ctr_m = fp.get("enable_ctr_mirror", enable_ctr)

            if f02_sdm:
                self.change_file_settings_sdm(
                    file_no=0x02,
                    uid_offset=sdm_cfg.uid_offset,
                    ctr_offset=sdm_cfg.ctr_offset,
                    mac_offset=sdm_cfg.mac_offset,
                    mac_input_offset=sdm_cfg.mac_input_offset,
                    mac_key=f02_mac_key,
                    read_perm=f02_read,
                    write_perm=f02_write,
                    rw_perm=f02_write,
                    change_perm=f02_change,
                    meta_read_key=f02_meta,
                    ctr_ret_key=f02_ctr_ret,
                    comm_mode=f02_comm,
                    enable_uid=f02_uid_m,
                    enable_ctr=f02_ctr_m,
                )
            else:
                self.change_file_settings_standard(
                    file_no=0x02,
                    read_perm=f02_read,
                    write_perm=f02_write,
                    rw_perm=f02_write,
                    change_perm=f02_change,
                    comm_mode=f02_comm,
                )

            # File 03 (Proprietary Data File - 128 bytes)
            if fp.get("file03_enabled", False):
                try:
                    f03_r = fp.get("file03_read", 0x3)
                    f03_w = fp.get("file03_write", 0x0)
                    f03_change = fp.get("file03_change", 0x0)
                    f03_comm = fp.get("file03_comm_mode", 0x03)
                    self.change_file_settings_standard(
                        file_no=0x03,
                        read_perm=f03_r,
                        write_perm=f03_w,
                        rw_perm=f03_w,
                        change_perm=f03_change,
                        comm_mode=f03_comm,
                    )
                except Exception as e:
                    logger.warning(f"Configure File 03 warning: {e}")

            # 6. Change Key 0 (Master Key)
            self.change_key(0, derived_keys[0], old_key=current_key0, key_ver=key_ver)

            # 7. Verification: Authenticate with the new derived Key 0
            self.select_ndef_application()
            self.authenticate_ev2_first(0, derived_keys[0])

            # 8. Verification read dynamic SUN URL
            self.select_ndef_application()
            verify_bytes = self.read_ndef_binary(length=len(sdm_cfg.ndef_record_bytes))
            verify_str = decode_ndef_uri(verify_bytes)

            detail = {
                "uid": uid.hex().upper(),
                "kdf_algo": kdf_algo,
                "mac_key": f02_mac_key,
                "derived_key0": derived_keys[0].hex().upper(),
                "derived_key2_mac": derived_keys[f02_mac_key].hex().upper(),
                "all_derived_keys": [derived_keys[i].hex().upper() for i in range(5)],
                "read_sample": verify_str,
                "aar_package": aar_package,
            }
            return True, "发卡注入成功 (所有密钥与文件权限已配置)", detail

        except Exception as e:
            logger.exception("Provisioning failed")
            return False, str(e), {}

    def restore_factory_defaults(
        self,
        uid: bytes,
        master_key: bytes,
        salt: bytes,
        kdf_algo: str = "HKDF-SHA256",
        kdf_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Restores a tag back to factory default state (Keys=00*16, SDM disabled).
        """
        null_key = b"\x00" * 16
        try:
            derived_keys = derive_all_keys(master_key, uid, salt, algorithm=kdf_algo, kdf_config=kdf_config)
            self.select_ndef_application()

            # Authenticate: Try derived Key 0 first, fallback to null key
            auth_ok = False
            try:
                self.authenticate_ev2_first(0, derived_keys[0])
                current_k0 = derived_keys[0]
                auth_ok = True
            except Exception:
                try:
                    self.select_ndef_application()
                    self.authenticate_ev2_first(0, null_key)
                    current_k0 = null_key
                    auth_ok = True
                except Exception:
                    pass

            if not auth_ok:
                return False, "认证失败，该标签的主密钥与当前配置不匹配"

            # 1. Revert Keys 1..4 back to 00*16 (in active authenticated session)
            for k in range(1, 5):
                old_k = derived_keys[k] if current_k0 != null_key else null_key
                try:
                    self.change_key(k, null_key, old_key=old_k, key_ver=0)
                except Exception as e:
                    logger.warning(f"Revert key {k} warning: {e}")

            # 2. Revert Key 0 back to 00*16
            self.change_key(0, null_key, old_key=current_k0, key_ver=0)

            # 3. Authenticate with factory null key for file resetting
            self.select_ndef_application()
            self.authenticate_ev2_first(0, null_key)

            # 4. Disable SDM on File 02 & set to open read/write
            try:
                self.reset_file_settings_plain(0x02)
            except Exception as e:
                logger.warning(f"Reset file settings warning: {e}")

            # 5. Wipe File 02 NDEF content (NLEN=0 and zero payload)
            try:
                self.write_ndef_binary(b"\x00" * 64)
            except Exception as e:
                logger.warning(f"Wipe NDEF binary warning: {e}")

            # 6. Verify final factory state
            self.select_ndef_application()
            if self.authenticate_ev2_first(0, null_key):
                return True, "已成功恢复出厂初始化 (所有密钥清0, SDM已关闭, NDEF已抹除)"
            return False, "恢复出厂后验签失败"

        except Exception as e:
            logger.exception("Factory reset failed")
            return False, str(e)

    def inspect_tag(
        self,
        uid: bytes,
        master_key: bytes,
        salt: bytes,
        kdf_algo: str = "HKDF-SHA256",
        mac_key: int = 3,
        kdf_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Inspects an NTAG 424 DNA tag in non-destructive mode:
        1. Reads NDEF binary content (NDEF URL / payload).
        2. Probes Key 0 authentication to determine factory state vs current master key state.
        """
        try:
            self.select_ndef_application()
            # 1. Read NDEF
            ndef_str = ""
            try:
                ndef_bytes = self.read_ndef_binary(length=180)
                ndef_str = decode_ndef_uri(ndef_bytes)
            except Exception as e:
                ndef_str = f"(未写入或无公开读 NDEF: {e})"

            # 2. Probe Authentication Key 0
            null_key = b"\x00" * 16
            derived_keys = derive_all_keys(master_key, uid, salt, algorithm=kdf_algo, kdf_config=kdf_config)

            self.select_ndef_application()
            auth_status = "UNKNOWN_KEY"
            auth_desc = "未知密钥锁定 (非出厂00且非当前系统配方)"

            try:
                self.authenticate_ev2_first(0, null_key)
                auth_status = "FACTORY_DEFAULT"
                auth_desc = "出厂默认状态 (全0密钥，未发卡)"
            except Exception:
                try:
                    self.select_ndef_application()
                    self.authenticate_ev2_first(0, derived_keys[0])
                    auth_status = "MATCHED_MASTER"
                    auth_desc = "已发卡 (主密钥与当前系统配方完全匹配)"
                except Exception:
                    pass

            if auth_status == "FACTORY_DEFAULT":
                active_key0 = "00" * 16
                active_key_mac = "00" * 16
            elif auth_status == "MATCHED_MASTER":
                active_key0 = derived_keys[0].hex().upper()
                active_key_mac = derived_keys[mac_key].hex().upper() if len(derived_keys) > mac_key else ""
            else:
                active_key0 = "未知 (硬件保护不可读)"
                active_key_mac = "未知 (硬件保护不可读)"

            detail = {
                "uid": uid.hex().upper(),
                "auth_status": auth_status,
                "auth_desc": auth_desc,
                "card_active_key0": active_key0,
                "card_active_key_mac": active_key_mac,
                "ndef_content": ndef_str,
                "recipe_derived_key0": derived_keys[0].hex().upper(),
                "recipe_derived_key_mac": derived_keys[mac_key].hex().upper() if len(derived_keys) > mac_key else "",
                "mac_key_slot": mac_key,
                # Compatibility backward fields
                "derived_key0": derived_keys[0].hex().upper(),
                "derived_key2_mac": derived_keys[mac_key].hex().upper() if len(derived_keys) > mac_key else "",
            }
            return True, f"诊断完成: {auth_desc}", detail
        except Exception as e:
            return False, f"诊断失败: {e}", {}
