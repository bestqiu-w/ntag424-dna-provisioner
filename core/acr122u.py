"""
ACR122U NFC Reader Manager via PC/SC.
Handles card connection, UID retrieval, APDU transmission, and Buzzer/LED hardware feedback.
"""

import time
from typing import Optional, Tuple, List
from smartcard.System import readers
from smartcard.CardConnection import CardConnection
from smartcard.scard import (
    SCARD_LEAVE_CARD,
    SCARD_UNPOWER_CARD,
    SCARD_STATE_UNAWARE,
    SCARD_STATE_PRESENT,
    SCARD_STATE_EMPTY,
    SCardGetStatusChange,
    SCARD_S_SUCCESS,
)
from smartcard.Exceptions import CardConnectionException, NoCardException


class ACR122UReader:
    """Manages connection to an ACS ACR122U NFC Reader."""

    APDU_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    # Hardware feedback APDUs (Pseudo-APDUs to reader firmware)
    # Green LED blink + 1 short beep (T1=100ms, T2=100ms, 1 rep -> 200ms)
    APDU_FEEDBACK_SUCCESS = [0xFF, 0x00, 0x40, 0x50, 0x04, 0x01, 0x01, 0x01, 0x01]
    # Red LED blink + 2 short beeps (T1=100ms, T2=100ms, 2 reps -> 400ms)
    APDU_FEEDBACK_FAILURE = [0xFF, 0x00, 0x40, 0xA0, 0x04, 0x01, 0x01, 0x02, 0x02]
    # Orange LED / 2 short beeps (T1=100ms, T2=100ms, 2 reps -> 400ms)
    APDU_FEEDBACK_WARNING = [0xFF, 0x00, 0x40, 0xF0, 0x04, 0x01, 0x01, 0x02, 0x01]

    def __init__(self, reader_name_filter: str = "ACR122"):
        self.reader_name_filter = reader_name_filter
        self.reader = None
        self.connection: Optional[CardConnection] = None
        self._is_connected = False
        self._current_uid: Optional[str] = None

    def find_reader(self) -> Optional[str]:
        """Find the first matching ACR122U reader attached to the system."""
        try:
            available_readers = readers()
        except Exception:
            if self.connection:
                try:
                    self.connection.release()
                except Exception:
                    pass
            self.reader = None
            self.connection = None
            self._is_connected = False
            self._current_uid = None
            return None

        matched_reader = None
        for r in available_readers:
            if self.reader_name_filter.lower() in str(r).lower():
                matched_reader = r
                break
        if not matched_reader and available_readers:
            matched_reader = available_readers[0]

        if matched_reader != self.reader:
            self.disconnect_card()
            if self.connection:
                try:
                    self.connection.release()
                except Exception:
                    pass
            self.reader = matched_reader
            self.connection = self.reader.createConnection() if self.reader else None

        return str(self.reader) if self.reader else None

    def connect_card(self) -> Tuple[bool, str]:
        """
        Polls for card on the reader without leaking PC/SC contexts or protocol locks.
        Uses SCardGetStatusChange for hardware-level presence detection without RF stress.
        Returns (success: bool, message/uid_hex: str).
        """
        if not self.reader:
            name = self.find_reader()
            if not name:
                return False, "未检测到读卡器，请插入 ACR122U"

        if not self.connection:
            try:
                self.connection = self.reader.createConnection()
            except Exception as e:
                return False, f"创建连接失败: {e}"

        # 1. 若当前已处于连接就绪状态，通过快速 APDU 获取 UID 确认卡片是否仍贴合在读卡区
        if self._is_connected and self.connection:
            try:
                data, sw1, sw2 = self.transmit(self.APDU_GET_UID)
                if sw1 == 0x90 and sw2 == 0x00:
                    uid = bytes(data).hex().upper()
                    self._current_uid = uid
                    return True, uid
            except Exception:
                pass

            # 瞬态抖动滤波：间隔 30ms 重试一次，避免射频瞬态扰动引起误触发
            time.sleep(0.03)
            try:
                data, sw1, sw2 = self.transmit(self.APDU_GET_UID)
                if sw1 == 0x90 and sw2 == 0x00:
                    uid = bytes(data).hex().upper()
                    self._current_uid = uid
                    return True, uid
            except Exception:
                pass

            # 确认卡片已离开感应区，干净断开并关闭射频供电
            self.disconnect_card()
            return False, "感应区未检测到卡片"

        # 2. 未连接卡片时：通过 SCardGetStatusChange 硬件探测卡片物理在席状态
        # 绝不盲目调用 connect()，彻底杜绝无卡状态下的射频高频空转与系统 PC/SC 资源死锁
        try:
            inner = getattr(self.connection, "component", self.connection)
            hcontext = getattr(inner, "hcontext", None)
            if hcontext is not None:
                readerstates = [(str(self.reader), SCARD_STATE_UNAWARE)]
                hresult, newstates = SCardGetStatusChange(hcontext, 0, readerstates)
                if hresult == SCARD_S_SUCCESS and newstates:
                    _r, state, _atr = newstates[0]
                    if not (state & SCARD_STATE_PRESENT):
                        # 硬件探测明确感应区无卡
                        return False, "感应区未检测到卡片"
        except Exception:
            pass

        # 3. 硬件已确认有卡片放置：建立全新卡片通信会话
        try:
            # 明确指定 T0 | T1 联合掩码，并设置 SCARD_UNPOWER_CARD 以便在断开时下电复位
            proto = CardConnection.T0_protocol | CardConnection.T1_protocol
            self.connection.connect(protocol=proto, disposition=SCARD_UNPOWER_CARD)
            data, sw1, sw2 = self.transmit(self.APDU_GET_UID)
            if sw1 == 0x90 and sw2 == 0x00:
                self._is_connected = True
                self._current_uid = bytes(data).hex().upper()
                return True, self._current_uid
            self.disconnect_card()
            return False, f"读取 UID 失败 (SW: {sw1:02X}{sw2:02X})"
        except NoCardException:
            self.disconnect_card()
            return False, "感应区未检测到卡片"
        except CardConnectionException as cce:
            self.disconnect_card()
            err_str = str(cce)
            if "0x80100003" in err_str or "0x80100009" in err_str or "0x8010001D" in err_str or "invalid handle" in err_str.lower() or "service not available" in err_str.lower():
                if self.connection:
                    try:
                        self.connection.release()
                    except Exception:
                        pass
                self.connection = None
                self.reader = None
            return False, "感应区未检测到卡片"
        except Exception as e:
            self.disconnect_card()
            err_str = str(e)
            if "0x80100003" in err_str or "0x80100009" in err_str or "0x8010001D" in err_str or "invalid handle" in err_str.lower() or "service not available" in err_str.lower():
                if self.connection:
                    try:
                        self.connection.release()
                    except Exception:
                        pass
                self.connection = None
                self.reader = None
            return False, f"读卡异常: {e}"

    def disconnect_card(self):
        """Disconnects current card session cleanly and unpowers card RF field."""
        if self.connection:
            try:
                inner = getattr(self.connection, "component", self.connection)
                if hasattr(inner, "disposition"):
                    inner.disposition = SCARD_UNPOWER_CARD
                if hasattr(inner, "hcard") and inner.hcard is not None:
                    inner.disconnect()
            except Exception:
                pass
            # 恢复内部协议掩码为 T0 | T1，防止 pyscard 协议固化为 T1 导致下次连接失败
            try:
                inner = getattr(self.connection, "component", self.connection)
                if hasattr(inner, "setProtocol"):
                    inner.setProtocol(CardConnection.T0_protocol | CardConnection.T1_protocol)
            except Exception:
                pass
        self._is_connected = False
        self._current_uid = None

    def reset_reader_connection(self) -> Tuple[bool, str]:
        """
        重置读卡器驱动连接与 PC/SC 上下文：
        1. 若有活动卡片，尝试强制关闭天线射频电源（SCARD_UNPOWER_CARD）并断开；
        2. 彻底释放底层 PC/SC 资源与上下文 (release)；
        3. 销毁旧 reader 与 connection 实例；
        4. 重新枚举并绑定读卡器硬件，完成全新初始化。
        """
        try:
            if self.connection:
                if self._is_connected:
                    try:
                        inner = getattr(self.connection, "component", self.connection)
                        if hasattr(inner, "disposition"):
                            inner.disposition = SCARD_UNPOWER_CARD
                        if hasattr(inner, "hcard") and inner.hcard is not None:
                            inner.disconnect()
                    except Exception:
                        pass
                try:
                    self.connection.disconnect()
                except Exception:
                    pass
                try:
                    self.connection.release()
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._is_connected = False
            self._current_uid = None
            self.connection = None
            self.reader = None

        # 稍作延时以便系统 PC/SC 守护进程完全回收资源
        time.sleep(0.3)

        # 重新扫描枚举读卡器硬件
        reader_name = self.find_reader()
        if reader_name:
            return True, f"读卡器驱动连接已重置成功: {reader_name}"
        else:
            return False, "重置完成，但未发现物理读卡器设备，请检查 USB 接口连接"

    def transmit(self, apdu: List[int]) -> Tuple[List[int], int, int]:
        """
        Transmits APDU bytes to the card or reader.
        Returns (response_data: List[int], sw1: int, sw2: int).
        """
        if not self.connection:
            raise ConnectionError("读卡器未连接任何卡片。")
        return self.connection.transmit(apdu)

    def set_hardware_buzzer(self, enabled: bool) -> bool:
        """
        Configure ACR122U hardware firmware PICC detection buzzer safely.
        Command: FF 00 52 [00 or FF] 00
        00h: Disable buzzer when card is detected (Silent mode).
        FFh: Enable buzzer when card is detected (Hardware default).
        Applied via standard card transmission to prevent macOS driver Direct Mode deadlocks.
        """
        buzz_byte = 0xFF if enabled else 0x00
        cmd = [0xFF, 0x00, 0x52, buzz_byte, 0x00]

        # Apply via active card connection safely
        if self.connection and self._is_connected:
            try:
                res, sw1, sw2 = self.transmit(cmd)
                return (sw1 == 0x90)
            except Exception:
                pass
        return False

    def trigger_success_feedback(self):
        """Beep 1 short + green LED (waits 0.25s for hardware buzzer completion)."""
        try:
            self.transmit(self.APDU_FEEDBACK_SUCCESS)
            time.sleep(0.25)
        except Exception:
            pass

    def trigger_failure_feedback(self):
        """Beep 2 short + red LED (waits 0.45s for hardware buzzer completion)."""
        try:
            self.transmit(self.APDU_FEEDBACK_FAILURE)
            time.sleep(0.45)
        except Exception:
            pass

    def trigger_warning_feedback(self):
        """Beep 2 short + orange LED (waits 0.45s for hardware buzzer completion)."""
        try:
            self.transmit(self.APDU_FEEDBACK_WARNING)
            time.sleep(0.45)
        except Exception:
            pass
