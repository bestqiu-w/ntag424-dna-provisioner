"""
Background NFC Worker Thread for ACR122U and NTAG 424 DNA.
Handles single-card inspection/provision/restore, continuous batch polling,
debouncing, and hardware sound/light feedback.
"""

import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from PySide6.QtCore import QThread, Signal

from core.acr122u import ACR122UReader
from core.ntag424 import NTAG424Manager

logger = logging.getLogger(__name__)


class NFCWorker(QThread):
    """Worker thread that interacts with ACR122U and NTAG 424 DNA cards."""

    # Signals
    reader_status = Signal(bool, str)             # connected: bool, name/info: str
    reader_reset_finished = Signal(bool, str)     # success: bool, message: str
    card_detected = Signal(str)                   # uid_hex: str
    card_removed = Signal()                       # card lifted from reader
    status_update = Signal(str, str)              # state_label: str, message: str
    log_message = Signal(str)                     # detail log string for UI log window
    tag_processed = Signal(dict)                  # record dictionary

    # Single Mode Granular Signals
    single_action_started = Signal(str)                      # action: 'provision' | 'restore' | 'inspect'
    single_action_finished = Signal(str, bool, str, dict)    # action, success, message, detail

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = ACR122UReader()
        self.running = False
        self.pending_reader_reset = False

        # Work Mode: "single" (default manual mode) or "batch" (continuous pipeline)
        self.work_mode = "single"

        # Batch sub-settings
        self.batch_mode = "provision"  # "provision" or "restore"
        self.batch_running = False     # whether batch continuous scanning is active

        # Single mode pending trigger: None | "provision" | "restore" | "inspect"
        self.pending_single_action: Optional[str] = None

        # Card presence tracking
        self.current_detected_uid: Optional[str] = None
        self.last_handled_uid: Optional[str] = None

        # Cryptographic and hardware configuration
        self.master_key = b"\x00" * 16
        self.system_salt = b"PATROL_SALT_2026"
        self.url_template = "https://patrol.example.com/v?u={UID}&c={CTR}&m={CMAC}"
        self.factory_key = b"\x00" * 16
        self.auto_buzzer = True
        self._hardware_buzzer_synced: Optional[bool] = None
        self.enable_aar = False
        self.aar_package_name = "com.example.patrol"
        self.kdf_algo = "HKDF-SHA256"
        self.mac_key = 3
        self.key_ver = 1
        self.enable_uid_mirror = True
        self.enable_ctr_mirror = True
        self.kdf_config: Dict[str, Any] = {}
        self.file_permissions: Dict[str, Any] = {}

    @property
    def paused(self) -> bool:
        if self.work_mode == "batch":
            return not self.batch_running
        return True

    def set_work_mode(self, mode: str):
        """Switch between 'single' (manual) and 'batch' (continuous)."""
        self.work_mode = mode
        self.pending_single_action = None
        self.last_handled_uid = None
        if mode == "single":
            if self.current_detected_uid:
                # 重新发射 card_detected，确保 MainWindow.current_card_uid 被正确赋值，单卡按钮立即可选
                self.card_detected.emit(self.current_detected_uid)
                self.status_update.emit("CARD_READY", f"已感应到卡片 [{self.current_detected_uid}]，请选择操作")
            else:
                self.card_removed.emit()
                self.status_update.emit("WAITING_SINGLE", "单卡调试模式已就绪，等待放置卡片")
            self.log_message.emit("[INFO] 切换至单卡调试模式")
        else:
            if self.batch_running:
                self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】正在等待卡片贴近...")
            else:
                self.status_update.emit("PAUSED", f"【批量{self.batch_mode_desc()}】处于暂停状态")
            self.log_message.emit("[INFO] 切换至批量自动模式")

    def batch_mode_desc(self) -> str:
        return "发卡注入" if self.batch_mode == "provision" else "恢复出厂"

    def set_batch_mode(self, mode: str):
        """Set batch action: 'provision' or 'restore'."""
        if self.batch_mode != mode:
            self.batch_mode = mode
            self.last_handled_uid = None  # 切换批量动作时重置防重记录，允许立即开始当前卡片
            if self.work_mode == "batch":
                if self.batch_running:
                    self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】正在等待卡片贴近...")
                else:
                    self.status_update.emit("PAUSED", f"【批量{self.batch_mode_desc()}】处于暂停状态")

    def start_batch(self):
        self.batch_running = True
        self.last_handled_uid = None  # 启动时清空防重，允许立即开始当前卡片
        self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】进行中，等待卡片...")
        self.log_message.emit(f"[INFO] 批量作业已启动: 模式【{self.batch_mode_desc()}】")

    def pause_batch(self):
        self.batch_running = False
        self.status_update.emit("PAUSED", f"【批量{self.batch_mode_desc()}】已暂停")
        self.log_message.emit("[INFO] 批量作业已暂停")

    def request_single_action(self, action: str):
        """Enqueue a single card action: 'provision', 'restore', or 'inspect'."""
        self.pending_single_action = action

    def request_reader_reset(self):
        """Request software reset of reader connection (simulates USB unplug & replug)."""
        self.pending_reader_reset = True

    def set_config(self, config: Dict[str, Any], mode: Optional[str] = None):
        if mode:
            self.batch_mode = mode

        try:
            m_hex = config.get("master_key", "").replace(" ", "").replace(":", "")
            self.master_key = bytes.fromhex(m_hex)
        except Exception:
            self.master_key = b"\x00" * 16

        try:
            f_hex = config.get("factory_key", "").replace(" ", "").replace(":", "")
            self.factory_key = bytes.fromhex(f_hex)
        except Exception:
            self.factory_key = b"\x00" * 16

        salt_str = config.get("system_salt", "")
        self.system_salt = salt_str.encode("utf-8") if isinstance(salt_str, str) else b""
        self.url_template = config.get("url_template", "")
        self.enable_aar = bool(config.get("enable_aar", False))
        self.aar_package_name = str(config.get("aar_package_name", "com.example.patrol")).strip()
        
        new_buzzer = bool(config.get("auto_buzzer", True))
        if self.auto_buzzer != new_buzzer:
            self.auto_buzzer = new_buzzer
            self._hardware_buzzer_synced = None
            if self.reader.connection:
                if self.reader.set_hardware_buzzer(self.auto_buzzer):
                    self._hardware_buzzer_synced = self.auto_buzzer

        self.kdf_config = {
            "algorithm": config.get("kdf_algorithm", "HKDF-SHA256"),
            "salt_source": config.get("kdf_salt_source", "UID_STR"),
            "custom_salt": config.get("kdf_custom_salt", config.get("system_salt", "")),
            "info_pattern": config.get("kdf_info_pattern", "ntag424|{UID}|{SLOT}"),
        }
        self.kdf_algo = self.kdf_config["algorithm"]
        self.mac_key = int(config.get("sdm_mac_key", 3))
        self.key_ver = int(config.get("key_version", 1))
        self.enable_uid_mirror = bool(config.get("enable_uid_mirror", True))
        self.enable_ctr_mirror = bool(config.get("enable_ctr_mirror", True))

        def _parse_hex_int(val, default):
            try:
                return int(str(val), 0) if isinstance(val, str) else int(val)
            except Exception:
                return default

        self.file_permissions = {
            "file01_enabled": bool(config.get("file01_enabled", False)),
            "file01_comm_mode": _parse_hex_int(config.get("file01_comm_mode", 0x00), 0x00),
            "file01_read": _parse_hex_int(config.get("file01_read", 0xE), 0xE),
            "file01_write": _parse_hex_int(config.get("file01_write", 0x0), 0x0),
            "file01_change": _parse_hex_int(config.get("file01_change", 0x0), 0x0),
            "file02_sdm": bool(config.get("file02_sdm", True)),
            "file02_comm_mode": _parse_hex_int(config.get("file02_comm_mode", 0x00), 0x00),
            "file02_read": _parse_hex_int(config.get("file02_read", 0xE), 0xE),
            "file02_write": _parse_hex_int(config.get("file02_write", 0x0), 0x0),
            "file02_change": _parse_hex_int(config.get("file02_change", 0x0), 0x0),
            "file02_meta_key": _parse_hex_int(config.get("file02_meta_key", 0xE), 0xE),
            "file02_ctr_ret_key": _parse_hex_int(config.get("file02_ctr_ret_key", 0xF), 0xF),
            "file02_mac_key": self.mac_key,
            "enable_uid_mirror": self.enable_uid_mirror,
            "enable_ctr_mirror": self.enable_ctr_mirror,
            "file03_enabled": bool(config.get("file03_enabled", False)),
            "file03_comm_mode": _parse_hex_int(config.get("file03_comm_mode", 0x03), 0x03),
            "file03_read": _parse_hex_int(config.get("file03_read", 0x3), 0x3),
            "file03_write": _parse_hex_int(config.get("file03_write", 0x0), 0x0),
            "file03_change": _parse_hex_int(config.get("file03_change", 0x0), 0x0),
        }

    def stop(self):
        self.running = False
        self.wait(2000)

    def run(self):
        self.running = True
        reader_connected = False

        while self.running:
            try:
                # 0. Check for manual software reader reset request
                if self.pending_reader_reset:
                    self.pending_reader_reset = False
                    self.log_message.emit("[INFO] 正在重置读卡器驱动连接并重新初始化 PC/SC 服务...")
                    self.current_detected_uid = None
                    self.last_handled_uid = None
                    self.card_removed.emit()
                    success, msg = self.reader.reset_reader_connection()
                    self._hardware_buzzer_synced = None
                    if success:
                        reader_connected = True
                        self.reader_status.emit(True, msg)
                        self.log_message.emit(f"[SUCCESS] {msg}")
                        if self.work_mode == "single":
                            self.status_update.emit("WAITING_SINGLE", "读卡器已重新就绪，等待放置卡片")
                        else:
                            if self.batch_running:
                                self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】正在等待卡片贴近...")
                            else:
                                self.status_update.emit("PAUSED", f"【批量{self.batch_mode_desc()}】处于暂停状态")
                        self.reader_reset_finished.emit(True, msg)
                    else:
                        reader_connected = False
                        self.reader_status.emit(False, "读卡器未就绪")
                        self.log_message.emit(f"[WARN] {msg}")
                        self.status_update.emit("NO_READER", "请检查并连接 ACR122U 读卡器")
                        self.reader_reset_finished.emit(False, msg)
                    time.sleep(0.3)
                    continue

                # 1. Reader presence check
                r_name = self.reader.find_reader()
                if not r_name:
                    if reader_connected:
                        reader_connected = False
                        self.reader_status.emit(False, "读卡器断开连接")
                        self.status_update.emit("NO_READER", "请连接 ACR122U 读卡器")
                        self.log_message.emit("[WARN] ACR122U 读卡器断开连接")
                    time.sleep(1.0)
                    continue
                else:
                    if not reader_connected:
                        reader_connected = True
                        self.reader_status.emit(True, f"已连接: {r_name}")
                        self.log_message.emit(f"[INFO] 读卡器已连接: {r_name}")
                        self._hardware_buzzer_synced = None
                        if self.work_mode == "single":
                            self.status_update.emit("WAITING_SINGLE", "单卡模式已就绪，等待放置卡片")
                        else:
                            if self.batch_running:
                                self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】正在等待卡片贴近...")
                            else:
                                self.status_update.emit("PAUSED", f"【批量{self.batch_mode_desc()}】处于暂停状态")

                # 2. Check for card presence
                has_card, uid_res = self.reader.connect_card()

                if not has_card:
                    if self.current_detected_uid is not None:
                        self.current_detected_uid = None
                        self.last_handled_uid = None
                        self.card_removed.emit()
                        if self.work_mode == "single":
                            self.status_update.emit("WAITING_SINGLE", "单卡调试模式已就绪，等待放置卡片")
                        elif self.batch_running:
                            self.status_update.emit("WAITING", f"【批量{self.batch_mode_desc()}】正在等待卡片贴近...")

                    # If user triggered single action while no card is on antenna:
                    if self.pending_single_action:
                        act_name = {"provision": "发卡注入", "restore": "恢复出厂", "inspect": "读取诊断"}.get(self.pending_single_action, self.pending_single_action)
                        self.pending_single_action = None
                        self.single_action_finished.emit(act_name, False, "未检测到卡片，请将标签置于读卡区", {})
                        self.status_update.emit("ERROR", f"执行【{act_name}】失败: 未检测到卡片")
                        self.log_message.emit(f"[WARN] 执行【{act_name}】失败: 感应区无卡片")

                    time.sleep(0.15)
                    continue

                uid_hex = uid_res

                # Ensure hardware buzzer state is synced when card is first present
                if self._hardware_buzzer_synced != self.auto_buzzer:
                    if self.reader.set_hardware_buzzer(self.auto_buzzer):
                        self._hardware_buzzer_synced = self.auto_buzzer

                if uid_hex != self.current_detected_uid:
                    self.current_detected_uid = uid_hex
                    self.card_detected.emit(uid_hex)
                    if self.work_mode == "single":
                        self.status_update.emit("CARD_READY", f"已感应到卡片 [UID: {uid_hex}]")
                        self.log_message.emit(f"[INFO] 感应到标签 UID: {uid_hex}")

                # --- SINGLE MODE ---
                if self.work_mode == "single":
                    if self.pending_single_action:
                        action = self.pending_single_action
                        self.pending_single_action = None
                        self.single_action_started.emit(action)
                        success, msg, detail, record = self._execute_card_action(action, uid_hex)
                        self.single_action_finished.emit(action, success, msg, detail)
                    time.sleep(0.15)
                    continue

                # --- BATCH CONTINUOUS MODE ---
                if not self.batch_running:
                    if uid_hex != getattr(self, "_last_paused_log_uid", None):
                        self._last_paused_log_uid = uid_hex
                        self.log_message.emit(f"[INFO] 感应到标签 UID: {uid_hex} (批量流水线暂停中)")
                    time.sleep(0.2)
                    continue

                # 运行中重置暂停提示记录
                self._last_paused_log_uid = None

                # Debounce check in batch: must lift card before processing next
                if uid_hex == self.last_handled_uid:
                    time.sleep(0.15)
                    continue

                # Process card automatically in batch
                self._execute_card_action(self.batch_mode, uid_hex)
                self.last_handled_uid = uid_hex
                time.sleep(0.2)
            except Exception as loop_err:
                self.log_message.emit(f"[WARN] 读卡器通信循环异常: {loop_err}")
                time.sleep(0.5)

    def _execute_card_action(self, action: str, uid_hex: str) -> Tuple[bool, str, Dict[str, Any], Dict[str, Any]]:
        """Execute one of 'provision', 'restore', or 'inspect' on the active card."""
        start_t = time.time()
        uid_bytes = bytes.fromhex(uid_hex)
        mgr = NTAG424Manager(self.reader.connection)

        action_names = {
            "provision": "发卡注入",
            "restore": "恢复出厂",
            "inspect": "读取诊断",
        }
        mode_name = action_names.get(action, action)

        self.status_update.emit("WRITING", f"正在执行【{mode_name}】 [UID: {uid_hex}]...")
        self.log_message.emit(f"[EXEC] 开始执行【{mode_name}】 [UID: {uid_hex}]")

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uid": uid_hex,
            "operation": mode_name,
            "status": "FAIL",
            "key0": "",
            "key_mac": "",
            "ndef_url": "",
            "duration_ms": 0,
            "details": "",
            "key2_mac": "",
        }
        detail: Dict[str, Any] = {}
        success = False
        msg = ""

        try:
            if action == "provision":
                aar_pkg = self.aar_package_name if self.enable_aar else None
                success, msg, detail = mgr.provision_tag(
                    uid=uid_bytes,
                    master_key=self.master_key,
                    salt=self.system_salt,
                    url_template=self.url_template,
                    current_key0=self.factory_key,
                    kdf_algo=self.kdf_algo,
                    mac_key=self.mac_key,
                    file_permissions=self.file_permissions,
                    key_ver=self.key_ver,
                    kdf_config=self.kdf_config,
                    aar_package=aar_pkg,
                )
                duration_ms = int((time.time() - start_t) * 1000)
                record["duration_ms"] = duration_ms
                record["details"] = msg
                if success:
                    record["status"] = "SUCCESS"
                    key0_full = detail.get("derived_key0", "")
                    mac_k_no = detail.get("mac_key", self.mac_key)
                    key_mac_full = detail.get("derived_key2_mac", "")
                    ndef_sample = detail.get("read_sample", "") or self.url_template

                    record["key0"] = key0_full
                    record["key_mac"] = key_mac_full
                    record["key2_mac"] = key_mac_full  # Full un-truncated key for table/CSV
                    record["ndef_url"] = ndef_sample
                    aar_info = f", AAR: {aar_pkg}" if aar_pkg else ""
                    record["details"] = f"算法: {self.kdf_algo}, MAC槽位: Key {mac_k_no}{aar_info}"

                    self.status_update.emit("SUCCESS", f"注入成功! UID: {uid_hex} (耗时: {duration_ms}ms)")
                    self.log_message.emit(f"[SUCCESS] 发卡注入完成 [UID: {uid_hex}, 耗时: {duration_ms}ms]:")
                    self.log_message.emit(f"  • 算法与配置: {self.kdf_algo} / 签名槽位: Key {mac_k_no}")
                    self.log_message.emit(f"  • 主控 Key 0: {key0_full}")
                    self.log_message.emit(f"  • 签名 Key {mac_k_no} (MAC): {key_mac_full}")
                    self.log_message.emit(f"  • NDEF 链接: {ndef_sample}")
                    if aar_pkg:
                        self.log_message.emit(f"  • AAR 关联应用: {aar_pkg} (已注入 Android Application Record)")
                    if self.auto_buzzer:
                        self.reader.trigger_success_feedback()
                else:
                    record["status"] = "ERROR"
                    self.status_update.emit("ERROR", f"注入失败: {msg}")
                    self.log_message.emit(f"[ERROR] 发卡注入失败: {msg}")
                    if self.auto_buzzer:
                        self.reader.trigger_failure_feedback()

            elif action == "restore":
                success, msg = mgr.restore_factory_defaults(
                    uid=uid_bytes,
                    master_key=self.master_key,
                    salt=self.system_salt,
                    kdf_algo=self.kdf_algo,
                    kdf_config=self.kdf_config,
                )
                duration_ms = int((time.time() - start_t) * 1000)
                record["duration_ms"] = duration_ms
                record["details"] = msg
                detail = {"uid": uid_hex, "msg": msg}
                if success:
                    record["status"] = "SUCCESS"
                    record["key0"] = "00" * 16
                    record["key_mac"] = "00" * 16
                    record["key2_mac"] = "00" * 16
                    record["ndef_url"] = "(已抹除清空)"
                    record["details"] = "所有密钥恢复出厂全 0 (00*16)，SDM 关闭，NDEF 已清空"

                    self.status_update.emit("SUCCESS", f"已恢复出厂! UID: {uid_hex} (耗时: {duration_ms}ms)")
                    self.log_message.emit(f"[SUCCESS] 恢复出厂完成 [UID: {uid_hex}, 耗时: {duration_ms}ms]:")
                    self.log_message.emit(f"  • 密钥状态: Keys 0..4 全部重置为出厂 00*16")
                    self.log_message.emit(f"  • 文件状态: SDM 镜像关闭，File 02 开放读写并清空数据")
                    if self.auto_buzzer:
                        self.reader.trigger_success_feedback()
                else:
                    record["status"] = "ERROR"
                    self.status_update.emit("ERROR", f"恢复出厂失败: {msg}")
                    self.log_message.emit(f"[ERROR] 恢复出厂失败: {msg}")
                    if self.auto_buzzer:
                        self.reader.trigger_failure_feedback()

            elif action == "inspect":
                success, msg, detail = mgr.inspect_tag(
                    uid=uid_bytes,
                    master_key=self.master_key,
                    salt=self.system_salt,
                    kdf_algo=self.kdf_algo,
                    mac_key=self.mac_key,
                    kdf_config=self.kdf_config,
                )
                duration_ms = int((time.time() - start_t) * 1000)
                record["duration_ms"] = duration_ms
                record["details"] = msg
                record["operation"] = "读取诊断"
                if success:
                    record["status"] = "SUCCESS"
                    auth_status = detail.get("auth_status", "")
                    auth_d = detail.get("auth_desc", "")
                    ndef_c = detail.get("ndef_content", "")
                    card_k0 = detail.get("card_active_key0", "")
                    card_km = detail.get("card_active_key_mac", "")
                    recipe_k0 = detail.get("recipe_derived_key0", "")
                    recipe_km = detail.get("recipe_derived_key_mac", "")

                    record["key0"] = card_k0
                    record["key_mac"] = card_km
                    record["key2_mac"] = card_km
                    record["ndef_url"] = ndef_c
                    record["details"] = auth_d

                    self.status_update.emit("SUCCESS", f"诊断完成! [{auth_d}]")
                    self.log_message.emit(f"[SUCCESS] 标签诊断完成 [UID: {uid_hex}, 耗时: {duration_ms}ms]:")
                    self.log_message.emit(f"  • 认证状态: {auth_d}")

                    if auth_status == "FACTORY_DEFAULT":
                        self.log_message.emit(f"  • 卡片当前实际 Key 0: 00000000000000000000000000000000 (出厂默认全0)")
                        if "(空白卡片" in ndef_c:
                            self.log_message.emit(f"  • NDEF 状态: 空白 (未写入数据)")
                        else:
                            self.log_message.emit(f"  • NDEF 数据: {ndef_c} (出厂预制/历史残留)")
                        self.log_message.emit(f"  • 当前配方就绪: 待注入 Key 0: {recipe_k0} (Key {self.mac_key}: {recipe_km})")
                    elif auth_status == "MATCHED_MASTER":
                        self.log_message.emit(f"  • 卡片生效 Key 0: {card_k0}")
                        self.log_message.emit(f"  • 卡片生效 Key {self.mac_key} (MAC): {card_km}")
                        self.log_message.emit(f"  • NDEF 链接: {ndef_c}")
                    else:
                        self.log_message.emit(f"  • 卡片当前 Key 0: 未知 (硬件保护不可读)")
                        self.log_message.emit(f"  • NDEF 数据: {ndef_c}")
                        self.log_message.emit(f"  • 提示: 该卡片已被其他系统主密钥锁定，与当前配方不匹配")

                    if self.auto_buzzer:
                        self.reader.trigger_success_feedback()
                else:
                    record["status"] = "ERROR"
                    self.status_update.emit("ERROR", f"诊断失败: {msg}")
                    self.log_message.emit(f"[ERROR] 诊断失败: {msg}")
                    if self.auto_buzzer:
                        self.reader.trigger_failure_feedback()
        finally:
            if success:
                # 仅在操作成功后重置卡片应用选择为 NDEF，方便外部 NFC 设备读取
                try:
                    mgr.select_ndef_application()
                except Exception:
                    pass
            else:
                # 失败时绝不向卡片发送额外 APDU，立即断开卡片连接，释放卡片与读卡器会话
                try:
                    self.reader.disconnect_card()
                except Exception:
                    pass

        self.tag_processed.emit(record)
        return success, msg, detail, record
