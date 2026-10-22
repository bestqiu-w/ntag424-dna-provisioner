"""
ACR122U NFC Reader Manager via PC/SC.
Handles card connection, UID retrieval, APDU transmission, and Buzzer/LED hardware feedback.
"""

from typing import Optional, Tuple, List
from smartcard.System import readers
from smartcard.CardConnection import CardConnection
from smartcard.scard import SCARD_LEAVE_CARD
from smartcard.Exceptions import CardConnectionException, NoCardException


class ACR122UReader:
    """Manages connection to an ACS ACR122U NFC Reader."""

    APDU_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    # Hardware feedback APDUs (Pseudo-APDUs to reader firmware)
    # Green LED blink + 1 short beep
    APDU_FEEDBACK_SUCCESS = [0xFF, 0x00, 0x40, 0x50, 0x04, 0x01, 0x01, 0x01, 0x01]
    # Red LED blink + 3 beeps
    APDU_FEEDBACK_FAILURE = [0xFF, 0x00, 0x40, 0xA0, 0x04, 0x02, 0x02, 0x03, 0x02]
    # Orange LED / Short alert
    APDU_FEEDBACK_WARNING = [0xFF, 0x00, 0x40, 0xF0, 0x04, 0x01, 0x01, 0x02, 0x01]

    def __init__(self, reader_name_filter: str = "ACR122"):
        self.reader_name_filter = reader_name_filter
        self.reader = None
        self.connection: Optional[CardConnection] = None
        self._is_connected = False

    def find_reader(self) -> Optional[str]:
        """Find the first matching ACR122U reader attached to the system."""
        try:
            available_readers = readers()
        except Exception:
            self.reader = None
            self.connection = None
            self._is_connected = False
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
            self.reader = matched_reader
            self.connection = self.reader.createConnection() if self.reader else None

        return str(self.reader) if self.reader else None

    def connect_card(self) -> Tuple[bool, str]:
        """
        Polls for card on the reader without leaking PC/SC contexts.
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

        # 1. If already connected, test if card is still present
        if self._is_connected:
            try:
                data, sw1, sw2 = self.transmit(self.APDU_GET_UID)
                if sw1 == 0x90 and sw2 == 0x00:
                    return True, bytes(data).hex().upper()
            except Exception:
                self.disconnect_card()

        # 2. Re-connect to card (reuses existing context handle)
        try:
            self.connection.connect(disposition=SCARD_LEAVE_CARD)
            data, sw1, sw2 = self.transmit(self.APDU_GET_UID)
            if sw1 == 0x90 and sw2 == 0x00:
                self._is_connected = True
                return True, bytes(data).hex().upper()
            self.disconnect_card()
            return False, f"读取 UID 失败 (SW: {sw1:02X}{sw2:02X})"
        except (NoCardException, CardConnectionException):
            self.disconnect_card()
            return False, "感应区未检测到卡片"
        except Exception as e:
            self.disconnect_card()
            return False, f"读卡异常: {e}"

    def disconnect_card(self):
        """Disconnects current card session cleanly without context leaks."""
        if self.connection and self._is_connected:
            try:
                self.connection.disconnect()
            except Exception:
                pass
        self._is_connected = False
        self.connection = None

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
        """Beep 1 short + green LED."""
        try:
            self.transmit(self.APDU_FEEDBACK_SUCCESS)
        except Exception:
            pass

    def trigger_failure_feedback(self):
        """Beep 3 times + red LED."""
        try:
            self.transmit(self.APDU_FEEDBACK_FAILURE)
        except Exception:
            pass

    def trigger_warning_feedback(self):
        """Beep 2 short + orange LED."""
        try:
            self.transmit(self.APDU_FEEDBACK_WARNING)
        except Exception:
            pass
