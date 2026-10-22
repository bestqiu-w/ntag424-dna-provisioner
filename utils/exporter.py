"""
Batch production log and audit CSV exporter.
"""

import csv
from typing import List, Dict, Any


def export_to_csv(arg1, arg2) -> bool:
    """
    Exports batch card issuance and inspection records to a standard audit CSV file.
    All keys are exported with FULL 32-character hex representations (never truncated).
    Supports either (records, filepath) or (filepath, records) parameter order for backward compatibility.
    """
    if isinstance(arg1, str):
        filepath = arg1
        records = arg2
    else:
        records = arg1
        filepath = arg2
    headers = [
        "记录时间",
        "卡片 UID",
        "作业类型",
        "执行状态",
        "主控密钥 Key 0",
        "SDM 签名密钥",
        "NDEF 链接 / 数据",
        "执行耗时(ms)",
        "执行结果与详情",
    ]

    try:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in records:
                # Retrieve full non-truncated keys
                k0 = r.get("key0") or r.get("derived_key0") or ""
                km = r.get("key_mac") or r.get("key2_mac_full") or r.get("key2_mac") or ""
                ndef = r.get("ndef_url") or r.get("ndef_content") or ""

                writer.writerow([
                    r.get("timestamp", ""),
                    r.get("uid", ""),
                    r.get("operation", ""),
                    r.get("status", ""),
                    k0,
                    km,
                    ndef,
                    r.get("duration_ms", 0),
                    r.get("details", ""),
                ])
        return True
    except Exception as e:
        print(f"Error exporting CSV: {e}")
        return False
