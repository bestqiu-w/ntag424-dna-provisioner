"""
NTAG 424 DNA - SDM (Secure Dynamic Messaging) & NDEF Payload Builder.
Calculates precise byte offsets for UID mirror, SDM read counter, and CMAC.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SDMConfig:
    url_template: str
    uid_offset: int
    ctr_offset: int
    mac_offset: int
    mac_input_offset: int
    ndef_record_bytes: bytes
    has_aar: bool = False
    aar_package: Optional[str] = None
    total_ndef_len: int = 0


# NDEF URI Identifier Codes (RTD URI)
URI_PREFIX_MAP = {
    "http://www.": 0x01,
    "https://www.": 0x02,
    "http://": 0x03,
    "https://": 0x04,
    "tel:": 0x05,
    "mailto:": 0x06,
}


def build_sdm_ndef(url_template: str, aar_package: Optional[str] = None) -> SDMConfig:
    """
    Builds the complete NDEF URI payload (with optional Android AAR record) for NTAG 424 DNA
    and calculates the precise byte offsets for File 02.

    Supported placeholders:
      {UID}  -> 14 characters hex (7 bytes UID)
      {CTR}  -> 6 characters hex (3 bytes Read Counter)
      {CMAC} -> 16 characters hex (8 bytes truncated MAC)

    When aar_package is supplied (e.g. 'com.example.patrol'), appends an Android Application Record (AAR)
    as Record 2, allowing Android phones to automatically launch the app while iPhones seamlessly
    open the URI verification landing page.
    """
    # Support NXP TagXplorer / TapLinx style placeholders (%04u, %SC, %016m, etc.)
    nxp_map = [
        ("%014u", "{UID}"), ("%014U", "{UID}"),
        ("%04u", "{UID}"), ("%04U", "{UID}"),
        ("%u", "{UID}"), ("%U", "{UID}"),
        ("%SC", "{CTR}"), ("%sc", "{CTR}"),
        ("%06c", "{CTR}"), ("%06C", "{CTR}"),
        ("%016m", "{CMAC}"), ("%016M", "{CMAC}"),
        ("%08m", "{CMAC}"), ("%08M", "{CMAC}"),
        ("%m", "{CMAC}"), ("%M", "{CMAC}"),
    ]
    for old, new in nxp_map:
        url_template = url_template.replace(old, new)

    # Normalize placeholders to uppercase
    url_template = (
        url_template.replace("{uid}", "{UID}")
        .replace("{ctr}", "{CTR}")
        .replace("{cmac}", "{CMAC}")
    )
    if "{UID}" not in url_template or "{CTR}" not in url_template or "{CMAC}" not in url_template:
        raise ValueError("URL 模板必须包含 {UID}、{CTR} 和 {CMAC} 占位符 (支持大小写)")

    # Match URI Prefix to optimize NDEF URI record length
    prefix_code = 0x00
    uri_body = url_template
    for prefix, code in URI_PREFIX_MAP.items():
        if url_template.startswith(prefix):
            prefix_code = code
            uri_body = url_template[len(prefix):]
            break

    # Use unique fixed-length temporary markers to safely locate exact offsets
    uid_marker = "U" * 14
    ctr_marker = "C" * 6
    cmac_marker = "M" * 16

    temp_body = (
        uri_body.replace("{UID}", uid_marker)
        .replace("{CTR}", ctr_marker)
        .replace("{CMAC}", cmac_marker)
    )

    uid_idx = temp_body.index(uid_marker)
    ctr_idx = temp_body.index(ctr_marker)
    cmac_idx = temp_body.index(cmac_marker)

    # Replace markers with zeros
    dummy_uri_body = (
        temp_body.replace(uid_marker, "0" * 14)
        .replace(ctr_marker, "0" * 6)
        .replace(cmac_marker, "0" * 16)
    )

    body_bytes = dummy_uri_body.encode("ascii")

    # Construct Record 1: NDEF URI Record
    payload_len = len(body_bytes) + 1
    if payload_len > 254:
        raise ValueError("URL 模板过长，超出了 Short Record NDEF 格式限制")

    clean_aar = aar_package.strip() if (aar_package and aar_package.strip()) else None

    # If AAR is appended, Record 1 has ME=0 (0x91); otherwise ME=1 (0xD1)
    uri_header_byte = 0x91 if clean_aar else 0xD1
    ndef_uri_header = bytes([
        uri_header_byte,  # MB=1, ME=0 (if AAR) / 1, SR=1, TNF=0x01 (Well-known)
        0x01,             # Type Length: 1
        payload_len,      # Payload Length
        0x55,             # Type: 'U'
        prefix_code       # Prefix code
    ])
    uri_record = ndef_uri_header + body_bytes

    # Construct Record 2: AAR Record (if requested)
    aar_record = b""
    if clean_aar:
        pkg_bytes = clean_aar.encode("utf-8")
        if len(pkg_bytes) > 200:
            raise ValueError(f"AAR 包名过长 ({len(pkg_bytes)} 字节)")
        type_aar = b"android.com:pkg"
        # MB=0, ME=1, SR=1, TNF=0x04 (NFC Forum External Type) -> 0x54
        aar_record = bytes([
            0x54,               # Flags: MB=0, ME=1, SR=1, TNF=0x04
            len(type_aar),      # Type Length: 15 (0x0F)
            len(pkg_bytes),     # Payload Length
        ]) + type_aar + pkg_bytes

    ndef_message = uri_record + aar_record
    nlen = len(ndef_message)

    if nlen + 2 > 256:
        raise ValueError(f"NDEF 载荷总长度 ({nlen + 2} 字节) 超出 NTAG 424 DNA File 02 标准容量 (256 字节)")

    # In NTAG 424 DNA File 02:
    # First 2 bytes are NLEN (big-endian 16-bit integer)
    # Followed immediately by the NDEF message
    full_file_data = bytes([nlen >> 8, nlen & 0xFF]) + ndef_message

    # Calculate offsets relative to the start of File 02:
    # 2 (NLEN) + 1 (Header) + 1 (TypeLen) + 1 (PayloadLen) + 1 (Type 'U') + 1 (PrefixCode) = 7 bytes
    uri_body_start_in_file = 7

    uid_offset = uri_body_start_in_file + uid_idx
    ctr_offset = uri_body_start_in_file + ctr_idx
    mac_offset = uri_body_start_in_file + cmac_idx

    # MAC Input Offset:
    # By default, covers from UID offset up to MAC offset
    mac_input_offset = uid_offset

    return SDMConfig(
        url_template=url_template,
        uid_offset=uid_offset,
        ctr_offset=ctr_offset,
        mac_offset=mac_offset,
        mac_input_offset=mac_input_offset,
        ndef_record_bytes=full_file_data,
        has_aar=bool(clean_aar),
        aar_package=clean_aar,
        total_ndef_len=nlen + 2,
    )


REVERSE_URI_PREFIX_MAP = {v: k for k, v in URI_PREFIX_MAP.items()}
REVERSE_URI_PREFIX_MAP[0x00] = ""


def decode_ndef_uri(raw_bytes: bytes) -> str:
    """
    Decodes raw NDEF File 02 bytes (NLEN + URI Record + optional AAR) into a clean, human-readable string.
    Correctly honors NLEN = 0 indicating an empty / unwritten card.
    Detects and displays secondary records such as Android Application Records (AAR).
    """
    if not raw_bytes or len(raw_bytes) < 2:
        return "(空白卡片 / 未写入数据)"

    # Offset 0..1: NLEN (2 bytes, big-endian integer length of NDEF message)
    nlen = (raw_bytes[0] << 8) | raw_bytes[1]
    if nlen == 0 or raw_bytes[:2] == b"\x00\x00":
        return "(空白卡片 / 未写入数据)"

    # If the file is all 0x00 or all 0xFF (unformatted / blank flash)
    if all(b == 0 for b in raw_bytes[:16]) or all(b == 0xFF for b in raw_bytes[:16]):
        return "(空白卡片 / 未写入数据)"

    uri_result = ""
    aar_result = ""

    try:
        if len(raw_bytes) >= 7 and nlen >= 4:
            msg_bytes = raw_bytes[2 : 2 + nlen]
            # Parse Record 1 (URI)
            r1_flags = msg_bytes[0]
            r1_type_len = msg_bytes[1]
            r1_payload_len = msg_bytes[2]
            r1_type = msg_bytes[3 : 3 + r1_type_len]
            if r1_type == b"U" and r1_payload_len > 1:
                prefix_code = msg_bytes[3 + r1_type_len]
                prefix_str = REVERSE_URI_PREFIX_MAP.get(prefix_code, "")
                uri_body = msg_bytes[3 + r1_type_len + 1 : 3 + r1_type_len + r1_payload_len].decode("utf-8", errors="ignore")
                uri_result = prefix_str + uri_body

            # Check if there is a Record 2 (e.g. AAR)
            r1_total_len = 3 + r1_type_len + r1_payload_len
            if len(msg_bytes) > r1_total_len + 3:
                r2_bytes = msg_bytes[r1_total_len:]
                r2_flags = r2_bytes[0]
                r2_type_len = r2_bytes[1]
                r2_payload_len = r2_bytes[2]
                r2_type = r2_bytes[3 : 3 + r2_type_len]
                if r2_type == b"android.com:pkg":
                    aar_pkg = r2_bytes[3 + r2_type_len : 3 + r2_type_len + r2_payload_len].decode("utf-8", errors="ignore")
                    aar_result = f" [AAR: {aar_pkg}]"

            if uri_result:
                return uri_result + aar_result
    except Exception:
        pass

    try:
        content = raw_bytes[2 : 2 + min(nlen, 128)].decode("utf-8", errors="ignore")
        if content.strip():
            return content
    except Exception:
        pass

    return "(空白卡片 / 未写入数据)"

