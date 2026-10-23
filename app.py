"""
NTAG 424 DNA 标签发卡与运维工具 (ntag424-dna-provisioner)
基于 PySide6 与 pyscard，支持 ACS ACR122U NFC 读写器。
"""

import sys
import os
import json
import re
import html
from datetime import datetime
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QFrame,
    QRadioButton,
    QButtonGroup,
    QTextEdit,
    QSplitter,
    QGroupBox,
    QStackedWidget,
    QSizePolicy,
)
from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QAbstractTableModel,
    QSortFilterProxyModel,
    QModelIndex,
    QUrl,
    QPointF,
)
from PySide6.QtGui import (
    QFont,
    QColor,
    QIcon,
    QAction,
    QKeySequence,
    QDesktopServices,
    QPen,
    QPixmap,
    QPainter,
)

from utils.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    generate_random_key,
    generate_random_recipe_name,
)
from utils.exporter import export_to_csv
from core.sdm_builder import build_sdm_ndef
from worker import NFCWorker


def populate_access_rights_combo(combo: QComboBox, default_val: str = "0xE"):
    combo.clear()
    options = [
        ("Free (0xE)", "0xE"),
        ("Key 0 (0x0)", "0x0"),
        ("Key 1 (0x1)", "0x1"),
        ("Key 2 (0x2)", "0x2"),
        ("Key 3 (0x3)", "0x3"),
        ("Key 4 (0x4)", "0x4"),
        ("Never (0xF)", "0xF"),
    ]
    for text, val in options:
        combo.addItem(text, val)
    idx = combo.findData(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def populate_comm_mode_combo(combo: QComboBox, default_val: str = "0x00"):
    combo.clear()
    options = [
        ("Plain (0x00)", "0x00"),
        ("MAC (0x01)", "0x01"),
        ("Full (0x03)", "0x03"),
    ]
    for text, val in options:
        combo.addItem(text, val)
    idx = combo.findData(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def populate_meta_read_combo(combo: QComboBox, default_val: str = "0xE"):
    combo.clear()
    options = [
        ("Free (0xE)", "0xE"),
        ("Key 0 (0x0)", "0x0"),
        ("Key 1 (0x1)", "0x1"),
        ("Key 2 (0x2)", "0x2"),
        ("Key 3 (0x3)", "0x3"),
        ("Key 4 (0x4)", "0x4"),
        ("Never (0xF)", "0xF"),
    ]
    for text, val in options:
        combo.addItem(text, val)
    idx = combo.findData(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def populate_ctr_ret_combo(combo: QComboBox, default_val: str = "0xF"):
    combo.clear()
    options = [
        ("Never (0xF)", "0xF"),
        ("Free (0xE)", "0xE"),
        ("Key 0 (0x0)", "0x0"),
        ("Key 1 (0x1)", "0x1"),
        ("Key 2 (0x2)", "0x2"),
        ("Key 3 (0x3)", "0x3"),
        ("Key 4 (0x4)", "0x4"),
    ]
    for text, val in options:
        combo.addItem(text, val)
    idx = combo.findData(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def populate_sdm_mac_combo(combo: QComboBox, default_val=3):
    combo.clear()
    options = [
        ("Key 3 (0x3)", 3),
        ("Key 2 (0x2)", 2),
        ("Key 1 (0x1)", 1),
        ("Key 0 (0x0)", 0),
        ("Key 4 (0x4)", 4),
    ]
    for text, val in options:
        combo.addItem(text, val)
    idx = combo.findData(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)


# ==============================================================================
# 弹窗 1: 配方快速一览弹窗 (Key-Value 概览)
# ==============================================================================
class RecipeSummaryDialog(QDialog):
    """弹出以 Key-Value 列表清晰展现当前生效配方的轻量窗口。"""

    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("发卡配方详情")
        self.resize(560, 480)
        self.config = config
        self.request_edit = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"当前配方详情: {self.config.get('recipe_name', '未命名配方')}")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setStyleSheet("color: #0F172A;")
        layout.addWidget(title)

        # Key-Value Table
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["配置项", "当前取值"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #CBD5E1;
                background-color: #FFFFFF;
                gridline-color: #F1F5F9;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                font-weight: bold;
                border: 1px solid #E2E8F0;
                padding: 4px;
            }
        """)

        self._populate_rows()
        layout.addWidget(self.table)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_edit = QPushButton("调整配方")
        btn_edit.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        btn_edit.clicked.connect(self._on_edit_clicked)
        btn_layout.addWidget(btn_edit)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #334155;
                padding: 6px 16px;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _on_edit_clicked(self):
        self.request_edit = True
        self.accept()

    def _populate_rows(self):
        c = self.config
        master_raw = c.get("master_key", "")
        master_mask = (master_raw[:4] + " ... " + master_raw[-4:]) if len(master_raw) == 32 else master_raw

        # Calculate offsets
        url = c.get("url_template", "")
        aar_pkg = c.get("aar_package_name") if c.get("enable_aar") else None
        offsets_str = "无"
        try:
            cfg = build_sdm_ndef(url, aar_package=aar_pkg)
            offsets_str = f"UID={cfg.uid_offset}, CTR={cfg.ctr_offset}, CMAC={cfg.mac_offset} (载荷: {cfg.total_ndef_len} / 256 B)"
        except Exception:
            pass

        # Build File permissions summary
        f01_status = f"启用 (Comm: {c.get('file01_comm_mode','0x00')}, R: {c.get('file01_read','0xE')}, W: {c.get('file01_write','0x0')})" if c.get("file01_enabled") else "未启用 (保持出厂)"
        f02_status = f"Comm: {c.get('file02_comm_mode','0x00')}, R: {c.get('file02_read','0xE')}, W: {c.get('file02_write','0x0')}, Change: {c.get('file02_change','0x0')}, Meta: {c.get('file02_meta_key','0xE')}"
        f03_status = f"启用 (Comm: {c.get('file03_comm_mode','0x03')}, R: {c.get('file03_read','0x3')}, W: {c.get('file03_write','0x0')})" if c.get("file03_enabled") else "未启用 (保持出厂)"

        items = [
            ("配方名称", c.get("recipe_name", "未命名")),
            ("密钥派生算法 (KDF)", c.get("kdf_algorithm", "HKDF-SHA256")),
            ("主密钥 (Master Key)", f"{master_mask} (16 字节)"),
            ("盐值策略 (Salt Source)", c.get("kdf_salt_source", "UID_STR")),
            ("自定义盐值", c.get("kdf_custom_salt", "(无)") if c.get("kdf_salt_source") == "CUSTOM" else "(绑定卡片 UID)"),
            ("派生上下文 (Info Context)", c.get("kdf_info_pattern", "ntag424|{UID}|{SLOT}")),
            ("SDM 签名槽位 (MAC Key)", f"Key {c.get('sdm_mac_key', 3)}"),
            ("NDEF 动态 URL 模板", url),
            ("Android AAR 记录", f"已启用 ({c.get('aar_package_name', '')})" if c.get("enable_aar") else "未启用"),
            ("动态偏移与容量", offsets_str),
            ("File 01 (CC 文件)", f01_status),
            ("File 02 (NDEF & SDM)", f02_status),
            ("File 03 (私有扩展文件)", f03_status),
            ("出厂验证密钥 (Factory Key)", c.get("factory_key", "00" * 16)),
        ]

        self.table.setRowCount(len(items))
        for row, (k, v) in enumerate(items):
            item_k = QTableWidgetItem(k)
            item_k.setFont(QFont("Arial", 10, QFont.Bold))
            item_k.setForeground(QColor("#334155"))
            item_v = QTableWidgetItem(str(v))
            item_v.setForeground(QColor("#0F172A"))
            self.table.setItem(row, 0, item_k)
            self.table.setItem(row, 1, item_v)


# ==============================================================================
# 弹窗 2: 配方调整与配置窗口 (RecipeEditDialog)
# ==============================================================================
class RecipeEditDialog(QDialog):
    """独立的配方配置编辑窗口，支持导入/导出与实时预览。"""

    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("发卡配方配置")
        self.resize(800, 610)
        self.setMinimumWidth(800)
        self.config = config.copy()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. Recipe Name (Required)
        name_card = QFrame()
        name_card.setStyleSheet("QFrame { background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 6px; }")
        nc_layout = QHBoxLayout(name_card)
        nc_layout.setContentsMargins(12, 8, 12, 8)
        nc_layout.setSpacing(10)

        lbl_r_name = QLabel("配方标识名称:")
        lbl_r_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #0F172A; border: none;")
        nc_layout.addWidget(lbl_r_name)

        self.input_recipe_name = QLineEdit()
        self.input_recipe_name.setPlaceholderText("请输入配方唯一标识名称")
        recipe_n = self.config.get("recipe_name", "").strip()
        if not recipe_n:
            recipe_n = generate_random_recipe_name()
        self.input_recipe_name.setText(recipe_n)
        self.input_recipe_name.setStyleSheet("background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 4px 8px; font-size: 12px; color: #0F172A; font-weight: 500;")
        nc_layout.addWidget(self.input_recipe_name)

        btn_rand_name = QPushButton("随机生成")
        btn_rand_name.setStyleSheet("background-color: #FFFFFF; color: #1E293B; border: 1px solid #CBD5E1; border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: 500;")
        btn_rand_name.clicked.connect(lambda: self.input_recipe_name.setText(generate_random_recipe_name()))
        nc_layout.addWidget(btn_rand_name)
        layout.addWidget(name_card)

        # 2. Main Tabs (Keys & SDM vs File Matrix)
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        chevron_path = ensure_chevron_icon(base_dir)
        check_path = ensure_check_icon(base_dir)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabBar::tab {{
                font-size: 13px;
                font-weight: bold;
                padding: 7px 22px;
                min-width: 140px;
                color: #334155;
            }}
            QTabBar::tab:selected {{
                background: #FFFFFF;
                border-bottom: 2px solid #2563EB;
                color: #1D4ED8;
            }}
            QCheckBox {{
                font-size: 12px;
                font-weight: 500;
                color: #0F172A;
                spacing: 7px;
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid #94A3B8;
                border-radius: 3px;
                background-color: #FFFFFF;
            }}
            QCheckBox::indicator:hover {{
                border-color: #2563EB;
            }}
            QCheckBox::indicator:checked {{
                border-color: #2563EB;
                background-color: #2563EB;
                image: url({check_path});
            }}
            QCheckBox::indicator:disabled {{
                border-color: #CBD5E1;
                background-color: #F1F5F9;
            }}
            QCheckBox:disabled {{
                color: #94A3B8;
            }}
            QComboBox {{
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #94A3B8;
                border-radius: 4px;
                padding: 3px 24px 3px 8px;
                font-size: 12px;
                min-height: 24px;
            }}
            QComboBox:hover {{
                border-color: #2563EB;
            }}
            QComboBox:focus {{
                border: 1.5px solid #2563EB;
            }}
            QComboBox:disabled {{
                background-color: #F8FAFC;
                color: #94A3B8;
                border-color: #CBD5E1;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: none;
            }}
            QComboBox::down-arrow {{
                image: url({chevron_path});
                width: 9px;
                height: 9px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #94A3B8;
                border-radius: 4px;
                padding: 3px;
                selection-background-color: #EFF6FF;
                selection-color: #1D4ED8;
            }}
            QLineEdit, QSpinBox {{
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
                color: #0F172A;
                min-height: 24px;
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border-color: #2563EB;
            }}
            QLineEdit:disabled, QSpinBox:disabled {{
                background-color: #F1F5F9;
                border: 1px solid #CBD5E1;
                color: #94A3B8;
            }}
            QLabel {{
                font-size: 12px;
                font-weight: 500;
                color: #0F172A;
            }}
            QLabel:disabled {{
                color: #94A3B8;
            }}
        """)

        # Sub-tab 1: 密钥与 SDM 规则
        tab_keys = QWidget()
        grid_keys = QGridLayout(tab_keys)
        grid_keys.setSpacing(8)
        grid_keys.setContentsMargins(12, 12, 12, 12)

        grid_keys.addWidget(QLabel("系统主密钥 (Master Key):"), 0, 0)
        self.input_master_key = QLineEdit()
        self.input_master_key.setPlaceholderText("32 位十六进制密钥，例如 00112233445566778899AABBCCDDEEFF")
        grid_keys.addWidget(self.input_master_key, 0, 1)

        btn_rand_key = QPushButton("随机密钥")
        btn_rand_key.setStyleSheet("background-color: #FFFFFF; color: #1E293B; border: 1px solid #CBD5E1; border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: 500;")
        btn_rand_key.clicked.connect(lambda: self.input_master_key.setText(generate_random_key()))
        grid_keys.addWidget(btn_rand_key, 0, 2)

        grid_keys.addWidget(QLabel("密钥派生算法 (KDF):"), 1, 0)
        self.combo_kdf = QComboBox()
        self.combo_kdf.addItem("HKDF-SHA256 (RFC 5869)", "HKDF-SHA256")
        self.combo_kdf.addItem("AES-128-CMAC (NXP AN10922)", "AES-128-CMAC")
        self.combo_kdf.addItem("HMAC-SHA256 (128-bit Truncated)", "HMAC-SHA256")
        self.combo_kdf.addItem("固定主密钥 (无派生)", "FIXED_KEY")
        self.combo_kdf.currentIndexChanged.connect(self.on_kdf_changed)
        grid_keys.addWidget(self.combo_kdf, 1, 1, 1, 2)

        self.lbl_salt_src = QLabel("派生盐值来源 (Salt):")
        grid_keys.addWidget(self.lbl_salt_src, 2, 0)
        self.combo_salt_src = QComboBox()
        self.combo_salt_src.addItem("卡片 UID 文本 (Hex-ASCII)", "UID_STR")
        self.combo_salt_src.addItem("卡片 UID 原始字节 (Binary)", "UID_BYTES")
        self.combo_salt_src.addItem("自定义全局盐值", "CUSTOM")
        self.combo_salt_src.addItem("无盐值 (空)", "NONE")
        self.combo_salt_src.currentIndexChanged.connect(self.on_salt_src_changed)
        grid_keys.addWidget(self.combo_salt_src, 2, 1, 1, 2)

        self.lbl_custom_salt = QLabel("自定义盐值 (Custom Salt):")
        grid_keys.addWidget(self.lbl_custom_salt, 3, 0)
        self.input_salt = QLineEdit()
        grid_keys.addWidget(self.input_salt, 3, 1, 1, 2)

        self.lbl_info_pattern = QLabel("派生上下文 (Info Context):")
        grid_keys.addWidget(self.lbl_info_pattern, 4, 0)
        self.input_info_pattern = QLineEdit()
        self.input_info_pattern.setPlaceholderText("支持变量: {UID}, {SLOT}，例如 ntag424|{UID}|{SLOT}")
        grid_keys.addWidget(self.input_info_pattern, 4, 1, 1, 2)

        grid_keys.addWidget(QLabel("SDM 签名密钥槽位 (MAC Key):"), 5, 0)
        self.combo_mac_key = QComboBox()
        populate_sdm_mac_combo(self.combo_mac_key, 3)
        grid_keys.addWidget(self.combo_mac_key, 5, 1, 1, 2)

        grid_keys.addWidget(QLabel("NDEF 动态 URL 模板:"), 6, 0)
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://example.com/v?u={UID}&c={CTR}&m={CMAC}")
        self.input_url.textChanged.connect(self.update_offset_preview)
        grid_keys.addWidget(self.input_url, 6, 1, 1, 2)

        grid_keys.addWidget(QLabel("Android AAR 记录:"), 7, 0)
        aar_box = QHBoxLayout()
        aar_box.setSpacing(20)
        self.chk_enable_aar = QCheckBox("追加 AAR")
        self.chk_enable_aar.stateChanged.connect(self.on_aar_toggle)
        aar_box.addWidget(self.chk_enable_aar)

        self.input_aar_pkg = QLineEdit()
        self.input_aar_pkg.setPlaceholderText("例如 com.example.patrol")
        self.input_aar_pkg.textChanged.connect(self.update_offset_preview)
        aar_box.addWidget(self.input_aar_pkg, 1)
        grid_keys.addLayout(aar_box, 7, 1, 1, 2)

        lbl_offset_title = QLabel("动态偏移与容量解析:")
        lbl_offset_title.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        grid_keys.addWidget(lbl_offset_title, 8, 0)
        self.lbl_offset_preview = QLabel("请输入包含 {UID}, {CTR}, {CMAC} 占位符的 URL 模板\n支持实时自动计算 File 02 偏移量与载荷用量")
        self.lbl_offset_preview.setFixedHeight(50)
        self.lbl_offset_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lbl_offset_preview.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.lbl_offset_preview.setStyleSheet("""
            color: #64748B;
            font-size: 11px;
            font-family: Menlo, Monaco, Consolas, monospace;
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 5px 10px;
        """)
        grid_keys.addWidget(self.lbl_offset_preview, 8, 1, 1, 2)

        grid_keys.addWidget(QLabel("出厂验证密钥 (Factory Key):"), 9, 0)
        self.input_factory_key = QLineEdit("00000000000000000000000000000000")
        grid_keys.addWidget(self.input_factory_key, 9, 1, 1, 2)

        self.tabs.addTab(tab_keys, "密钥派生与 SDM 规则")

        # Sub-tab 2: 文件访问权限矩阵 (规范一体化卡片架构，与整体 UI 框架大风格完全统一)
        tab_files = QWidget()
        layout_files = QVBoxLayout(tab_files)
        layout_files.setSpacing(10)
        layout_files.setContentsMargins(10, 10, 10, 10)

        def _make_unified_card(title: str, subtitle: str = "", is_subcard: bool = False):
            card = QFrame()
            if is_subcard:
                card.setStyleSheet("""
                    QFrame#sub_card {
                        background-color: #F8FAFC;
                        border: 1px solid #E2E8F0;
                        border-radius: 6px;
                    }
                """)
                card.setObjectName("sub_card")
            else:
                card.setStyleSheet("""
                    QFrame#main_card {
                        background-color: #FFFFFF;
                        border: 1px solid #CBD5E1;
                        border-radius: 6px;
                    }
                """)
                card.setObjectName("main_card")

            card_l = QVBoxLayout(card)
            card_l.setContentsMargins(0, 0, 0, 0)
            card_l.setSpacing(0)

            # 一体化标题行 (无突兀双色块，强化标题与副标字号色深)
            t_box = QHBoxLayout()
            if is_subcard:
                t_box.setContentsMargins(12, 8, 12, 6)
            else:
                t_box.setContentsMargins(14, 10, 14, 7)
            t_box.setSpacing(8)

            lbl_t = QLabel(title)
            if is_subcard:
                lbl_t.setStyleSheet("font-size: 12px; font-weight: bold; color: #0F172A; border: none; background: transparent;")
            else:
                lbl_t.setStyleSheet("font-size: 13px; font-weight: bold; color: #0F172A; border: none; background: transparent;")
            t_box.addWidget(lbl_t)

            if subtitle:
                lbl_s = QLabel(subtitle)
                lbl_s.setStyleSheet("font-size: 12px; color: #475569; font-weight: 500; border: none; background: transparent;")
                t_box.addWidget(lbl_s)

            t_box.addStretch()
            card_l.addLayout(t_box)

            # 1px 细分割线：清晰分隔标题与下方配置内容，杜绝内容紧塞挤靠
            div = QFrame()
            div.setFrameShape(QFrame.HLine)
            div.setStyleSheet("color: #E2E8F0; margin: 0px 8px;")
            card_l.addWidget(div)

            # 内容主体区 (使用对象选择器，避免 border: none 污染并清空内部下拉框边框)
            body = QWidget()
            body.setObjectName("card_body")
            body.setStyleSheet("QWidget#card_body { background: transparent; border: none; }")
            body_l = QVBoxLayout(body)
            if is_subcard:
                body_l.setContentsMargins(12, 9, 12, 9)
            else:
                body_l.setContentsMargins(14, 11, 14, 11)
            body_l.setSpacing(8)
            card_l.addWidget(body)

            return card, body_l

        # 1. File 02 (NDEF 交互文件，包含基础权限与专属 SDM 动态特性)
        card_f02, body_f02 = _make_unified_card("File 02 (NDEF 交互文件)", "(256 字节 / 动态防伪)")

        # File 02 基础安全访问权限
        grid_f02_std = QGridLayout()
        grid_f02_std.setSpacing(8)

        grid_f02_std.addWidget(QLabel("通信模式 (CommMode):"), 0, 0)
        self.combo_f02_comm = QComboBox()
        populate_comm_mode_combo(self.combo_f02_comm, "0x00")
        grid_f02_std.addWidget(self.combo_f02_comm, 0, 1)

        grid_f02_std.addWidget(QLabel("读权限 (Read Perm):"), 0, 2)
        self.combo_f02_read = QComboBox()
        populate_access_rights_combo(self.combo_f02_read, "0xE")
        grid_f02_std.addWidget(self.combo_f02_read, 0, 3)

        grid_f02_std.addWidget(QLabel("写权限 (Write Perm):"), 1, 0)
        self.combo_f02_write = QComboBox()
        populate_access_rights_combo(self.combo_f02_write, "0x0")
        grid_f02_std.addWidget(self.combo_f02_write, 1, 1)

        grid_f02_std.addWidget(QLabel("修改权限 (Change Perm):"), 1, 2)
        self.combo_f02_change = QComboBox()
        populate_access_rights_combo(self.combo_f02_change, "0x0")
        grid_f02_std.addWidget(self.combo_f02_change, 1, 3)

        body_f02.addLayout(grid_f02_std)

        # File 02 专有特性：SDM 动态特性子卡片 (明确归属 File 02，拥有清晰标题区与分割线)
        card_sdm, body_sdm = _make_unified_card("SDM 动态安全特性 (Secure Dynamic Messaging / SUN)", "(动态签名 / 鉴权)", is_subcard=True)

        self.chk_f02_sdm = QCheckBox("启用 SDM 动态签名 (SUN)")
        self.chk_f02_sdm.setChecked(True)
        self.chk_f02_sdm.setStyleSheet("font-size: 12px; font-weight: bold; color: #0F172A;")
        body_sdm.addWidget(self.chk_f02_sdm)

        self.widget_sdm_sub = QWidget()
        l_sdm_sub = QVBoxLayout(self.widget_sdm_sub)
        l_sdm_sub.setContentsMargins(18, 0, 0, 0)
        l_sdm_sub.setSpacing(6)

        h_mirrors = QHBoxLayout()
        h_mirrors.setSpacing(28)
        self.chk_uid_mirror = QCheckBox("镜像 UID (硬件唯一识别码)")
        self.chk_uid_mirror.setChecked(True)
        self.chk_ctr_mirror = QCheckBox("镜像计数器 (防重放动态累加)")
        self.chk_ctr_mirror.setChecked(True)
        h_mirrors.addWidget(self.chk_uid_mirror)
        h_mirrors.addWidget(self.chk_ctr_mirror)
        h_mirrors.addStretch()
        l_sdm_sub.addLayout(h_mirrors)

        grid_sdm_keys = QGridLayout()
        grid_sdm_keys.setSpacing(6)
        self.lbl_f02_meta = QLabel("元数据加密 (MetaRead):")
        grid_sdm_keys.addWidget(self.lbl_f02_meta, 0, 0)
        self.combo_f02_meta = QComboBox()
        populate_meta_read_combo(self.combo_f02_meta, "0xE")
        grid_sdm_keys.addWidget(self.combo_f02_meta, 0, 1)

        self.lbl_f02_ctr_ret = QLabel("计数器回读 (CtrRet):")
        grid_sdm_keys.addWidget(self.lbl_f02_ctr_ret, 0, 2)
        self.combo_f02_ctr_ret = QComboBox()
        populate_ctr_ret_combo(self.combo_f02_ctr_ret, "0xF")
        grid_sdm_keys.addWidget(self.combo_f02_ctr_ret, 0, 3)
        l_sdm_sub.addLayout(grid_sdm_keys)

        body_sdm.addWidget(self.widget_sdm_sub)
        self.chk_f02_sdm.toggled.connect(self.on_f02_sdm_toggled)

        body_f02.addWidget(card_sdm)
        layout_files.addWidget(card_f02)

        # 2. File 01 & File 03 (底部双列对称卡片)
        h_files_layout = QHBoxLayout()
        h_files_layout.setSpacing(10)

        # File 01 Unified Card
        card_f01, body_f01 = _make_unified_card("File 01 (CC 描述文件)", "(32 字节)")

        self.chk_f01_en = QCheckBox("同步配置 File 01")
        self.chk_f01_en.setStyleSheet("font-size: 12px; font-weight: bold; color: #0F172A;")
        self.chk_f01_en.toggled.connect(self.on_f01_en_toggled)
        body_f01.addWidget(self.chk_f01_en)

        self.widget_f01_fields = QWidget()
        grid_f01 = QGridLayout(self.widget_f01_fields)
        grid_f01.setContentsMargins(0, 0, 0, 0)
        grid_f01.setSpacing(6)
        grid_f01.addWidget(QLabel("通信模式:"), 0, 0)
        self.combo_f01_comm = QComboBox()
        populate_comm_mode_combo(self.combo_f01_comm, "0x00")
        grid_f01.addWidget(self.combo_f01_comm, 0, 1)

        grid_f01.addWidget(QLabel("读权限:"), 1, 0)
        self.combo_f01_read = QComboBox()
        populate_access_rights_combo(self.combo_f01_read, "0xE")
        grid_f01.addWidget(self.combo_f01_read, 1, 1)

        grid_f01.addWidget(QLabel("写权限:"), 2, 0)
        self.combo_f01_write = QComboBox()
        populate_access_rights_combo(self.combo_f01_write, "0x0")
        grid_f01.addWidget(self.combo_f01_write, 2, 1)

        grid_f01.addWidget(QLabel("修改权限:"), 3, 0)
        self.combo_f01_change = QComboBox()
        populate_access_rights_combo(self.combo_f01_change, "0x0")
        grid_f01.addWidget(self.combo_f01_change, 3, 1)
        body_f01.addWidget(self.widget_f01_fields)

        h_files_layout.addWidget(card_f01)

        # File 03 Unified Card
        card_f03, body_f03 = _make_unified_card("File 03 (私有扩展文件)", "(128 字节)")

        self.chk_f03_en = QCheckBox("同步配置 File 03")
        self.chk_f03_en.setStyleSheet("font-size: 12px; font-weight: bold; color: #0F172A;")
        self.chk_f03_en.toggled.connect(self.on_f03_en_toggled)
        body_f03.addWidget(self.chk_f03_en)

        self.widget_f03_fields = QWidget()
        grid_f03 = QGridLayout(self.widget_f03_fields)
        grid_f03.setContentsMargins(0, 0, 0, 0)
        grid_f03.setSpacing(6)
        grid_f03.addWidget(QLabel("通信模式:"), 0, 0)
        self.combo_f03_comm = QComboBox()
        populate_comm_mode_combo(self.combo_f03_comm, "0x03")
        grid_f03.addWidget(self.combo_f03_comm, 0, 1)

        grid_f03.addWidget(QLabel("读权限:"), 1, 0)
        self.combo_f03_read = QComboBox()
        populate_access_rights_combo(self.combo_f03_read, "0x3")
        grid_f03.addWidget(self.combo_f03_read, 1, 1)

        grid_f03.addWidget(QLabel("写权限:"), 2, 0)
        self.combo_f03_write = QComboBox()
        populate_access_rights_combo(self.combo_f03_write, "0x0")
        grid_f03.addWidget(self.combo_f03_write, 2, 1)

        grid_f03.addWidget(QLabel("修改权限:"), 3, 0)
        self.combo_f03_change = QComboBox()
        populate_access_rights_combo(self.combo_f03_change, "0x0")
        grid_f03.addWidget(self.combo_f03_change, 3, 1)
        body_f03.addWidget(self.widget_f03_fields)

        h_files_layout.addWidget(card_f03)
        layout_files.addLayout(h_files_layout)

        self.tabs.addTab(tab_files, "文件安全访问权限")
        layout.addWidget(self.tabs)

        # 3. Bottom Action Bar (Import/Export on Left, Cancel/Save on Right)
        bottom_bar = QHBoxLayout()

        btn_import = QPushButton("导入配方文件")
        btn_import.setStyleSheet("background-color: #F8FAFC; color: #1E293B; border: 1px solid #CBD5E1; border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 500;")
        btn_import.clicked.connect(self.import_recipe)
        bottom_bar.addWidget(btn_import)

        btn_export = QPushButton("导出配方文件")
        btn_export.setStyleSheet("background-color: #F8FAFC; color: #1E293B; border: 1px solid #CBD5E1; border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 500;")
        btn_export.clicked.connect(self.export_recipe)
        bottom_bar.addWidget(btn_export)

        bottom_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("background-color: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; border-radius: 4px; padding: 6px 18px; font-size: 12px; font-weight: 500;")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("保存并应用配方")
        btn_save.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; border: none; border-radius: 4px; padding: 6px 20px; font-size: 12px;")
        btn_save.clicked.connect(self.save_and_apply)
        bottom_bar.addWidget(btn_save)

        layout.addLayout(bottom_bar)

        # Load values into UI
        self.load_values_to_ui()

    def on_kdf_changed(self):
        kdf = self.combo_kdf.currentData() or "HKDF-SHA256"
        is_fixed = ("FIXED" in kdf)

        if "CMAC" in kdf:
            self.input_info_pattern.setText("NXP")
        elif not is_fixed:
            if self.input_info_pattern.text().strip() in ("", "NXP"):
                self.input_info_pattern.setText("ntag424|{UID}|{SLOT}")

        self.combo_salt_src.setEnabled(not is_fixed)
        if hasattr(self, "lbl_salt_src"):
            self.lbl_salt_src.setEnabled(not is_fixed)
        self.input_info_pattern.setEnabled(not is_fixed)
        if hasattr(self, "lbl_info_pattern"):
            self.lbl_info_pattern.setEnabled(not is_fixed)

        if is_fixed:
            self.input_salt.setEnabled(False)
            if hasattr(self, "lbl_custom_salt"):
                self.lbl_custom_salt.setEnabled(False)
            txt = self.input_salt.text().strip()
            if txt:
                self._custom_salt_cache = txt
            self.input_salt.clear()
            self.input_salt.setPlaceholderText("（固定主密钥模式下不使用盐值）")
            self.input_info_pattern.setPlaceholderText("（固定主密钥模式下无需派生上下文）")
        else:
            self.input_info_pattern.setPlaceholderText("支持变量: {UID}, {SLOT}，例如 ntag424|{UID}|{SLOT}")
            self.on_salt_src_changed()

    def on_salt_src_changed(self):
        src = self.combo_salt_src.currentData() or "UID_STR"
        is_custom = (src == "CUSTOM")

        if hasattr(self, "lbl_custom_salt"):
            self.lbl_custom_salt.setEnabled(is_custom)
        self.input_salt.setEnabled(is_custom)

        if is_custom:
            if not self.input_salt.text().strip():
                cached = getattr(self, "_custom_salt_cache", "")
                if cached:
                    self.input_salt.setText(cached)
            self.input_salt.setPlaceholderText("请输入自定义项目盐值，例如 PATROL_SYSTEM_2026")
        else:
            txt = self.input_salt.text().strip()
            if txt:
                self._custom_salt_cache = txt
            self.input_salt.clear()
            if src in ("UID_STR", "UID_HEX", "UID"):
                self.input_salt.setPlaceholderText("（已自动绑定卡片硬件 UID 文本作为盐值）")
            elif src in ("UID_BYTES", "UID_BIN"):
                self.input_salt.setPlaceholderText("（已自动绑定卡片 7 字节原始 UID 字节流）")
            elif src in ("NONE", "EMPTY"):
                self.input_salt.setPlaceholderText("（无派生盐值 / 留空）")
            else:
                self.input_salt.setPlaceholderText("（当前盐值模式下不可编辑）")

    def on_aar_toggle(self):
        enabled = self.chk_enable_aar.isChecked()
        self.input_aar_pkg.setEnabled(enabled)
        self.update_offset_preview()

    def on_f02_sdm_toggled(self, checked: bool):
        self.widget_sdm_sub.setEnabled(checked)

    def on_f01_en_toggled(self, checked: bool):
        self.widget_f01_fields.setEnabled(checked)

    def on_f03_en_toggled(self, checked: bool):
        self.widget_f03_fields.setEnabled(checked)

    def update_offset_preview(self):
        url = self.input_url.text().strip()
        aar_pkg = self.input_aar_pkg.text().strip() if self.chk_enable_aar.isChecked() else None
        try:
            cfg = build_sdm_ndef(url, aar_package=aar_pkg)
            remain = 256 - len(cfg.ndef_record_bytes)
            line1 = f"动态偏移: UID = {cfg.uid_offset} B  |  计数器 = {cfg.ctr_offset} B  |  CMAC = {cfg.mac_offset} B"
            line2 = f"容器载荷: {len(cfg.ndef_record_bytes)} / 256 字节 (剩余 {remain} 字节)"
            self.lbl_offset_preview.setText(f"{line1}\n{line2}")
            self.lbl_offset_preview.setStyleSheet("""
                color: #0F766E;
                font-size: 11px;
                font-family: Menlo, Monaco, Consolas, monospace;
                background-color: #F0FDFA;
                border: 1px solid #CCFBF1;
                border-radius: 6px;
                padding: 5px 10px;
            """)
        except Exception as e:
            line1 = "⚠️ 模板格式校验未通过: 缺少必要占位参数"
            line2 = "URL 需包含 {UID} (14位)、{CTR} (6位) 和 {CMAC} (16位) 动态参数"
            self.lbl_offset_preview.setText(f"{line1}\n{line2}")
            self.lbl_offset_preview.setStyleSheet("""
                color: #B91C1C;
                font-size: 11px;
                font-family: Menlo, Monaco, Consolas, monospace;
                background-color: #FEF2F2;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 5px 10px;
            """)

    def load_values_to_ui(self):
        c = self.config
        self.input_recipe_name.setText(c.get("recipe_name", generate_random_recipe_name()))
        self.input_master_key.setText(c.get("master_key", ""))
        self._custom_salt_cache = c.get("kdf_custom_salt", c.get("system_salt", ""))
        self.input_salt.setText(self._custom_salt_cache)
        self.input_factory_key.setText(c.get("factory_key", "00" * 16))
        self.input_url.setText(c.get("url_template", ""))
        self.chk_enable_aar.setChecked(bool(c.get("enable_aar", False)))
        self.input_aar_pkg.setText(c.get("aar_package_name", "com.example.patrol"))
        self.input_aar_pkg.setEnabled(self.chk_enable_aar.isChecked())

        def _set_combo(combo, val):
            idx = combo.findData(str(val))
            if idx < 0:
                idx = combo.findData(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        _set_combo(self.combo_kdf, c.get("kdf_algorithm", "HKDF-SHA256"))
        _set_combo(self.combo_salt_src, c.get("kdf_salt_source", "UID_STR"))
        self.input_info_pattern.setText(c.get("kdf_info_pattern", "ntag424|{UID}|{SLOT}"))
        self.on_kdf_changed()

        # File 02
        _set_combo(self.combo_f02_comm, c.get("file02_comm_mode", "0x00"))
        _set_combo(self.combo_f02_read, c.get("file02_read", "0xE"))
        _set_combo(self.combo_f02_write, c.get("file02_write", "0x0"))
        _set_combo(self.combo_f02_change, c.get("file02_change", "0x0"))
        _set_combo(self.combo_mac_key, int(c.get("sdm_mac_key", 3)))
        _set_combo(self.combo_f02_meta, c.get("file02_meta_key", "0xE"))
        _set_combo(self.combo_f02_ctr_ret, c.get("file02_ctr_ret_key", "0xF"))

        self.chk_f02_sdm.setChecked(c.get("file02_sdm", True))
        self.chk_uid_mirror.setChecked(c.get("enable_uid_mirror", True))
        self.chk_ctr_mirror.setChecked(c.get("enable_ctr_mirror", True))
        self.on_f02_sdm_toggled(self.chk_f02_sdm.isChecked())

        # File 01
        self.chk_f01_en.setChecked(c.get("file01_enabled", False))
        self.on_f01_en_toggled(self.chk_f01_en.isChecked())
        _set_combo(self.combo_f01_comm, c.get("file01_comm_mode", "0x00"))
        _set_combo(self.combo_f01_read, c.get("file01_read", "0xE"))
        _set_combo(self.combo_f01_write, c.get("file01_write", "0x0"))
        _set_combo(self.combo_f01_change, c.get("file01_change", "0x0"))

        # File 03
        self.chk_f03_en.setChecked(c.get("file03_enabled", False))
        self.on_f03_en_toggled(self.chk_f03_en.isChecked())
        _set_combo(self.combo_f03_comm, c.get("file03_comm_mode", "0x03"))
        _set_combo(self.combo_f03_read, c.get("file03_read", "0x3"))
        _set_combo(self.combo_f03_write, c.get("file03_write", "0x0"))
        _set_combo(self.combo_f03_change, c.get("file03_change", "0x0"))

        self.update_offset_preview()

    def get_values_from_ui(self) -> Optional[Dict[str, Any]]:
        name = self.input_recipe_name.text().strip()
        if not name:
            QMessageBox.warning(self, "必填项缺失", "请输入【配方名称】后再保存或导出。")
            self.input_recipe_name.setFocus()
            return None

        m_hex = self.input_master_key.text().strip().replace(" ", "").replace(":", "")
        if len(m_hex) != 32:
            QMessageBox.warning(self, "参数错误", "Master Key 必须为 32 位十六进制字符 (16 字节 AES 密钥)。")
            self.input_master_key.setFocus()
            return None

        cfg = self.config.copy()
        cfg["recipe_name"] = name
        cfg["master_key"] = m_hex.upper()
        cfg["factory_key"] = self.input_factory_key.text().strip().upper()
        cfg["url_template"] = self.input_url.text().strip()
        cfg["enable_aar"] = self.chk_enable_aar.isChecked()
        cfg["aar_package_name"] = self.input_aar_pkg.text().strip()
        cfg["key_version"] = int(self.config.get("key_version", 1))

        cfg["kdf_algorithm"] = self.combo_kdf.currentData()
        cfg["kdf_salt_source"] = self.combo_salt_src.currentData()
        if cfg["kdf_salt_source"] == "CUSTOM":
            custom_salt_val = self.input_salt.text().strip()
        else:
            custom_salt_val = getattr(self, "_custom_salt_cache", "") or self.config.get("kdf_custom_salt", "")
        cfg["kdf_custom_salt"] = custom_salt_val
        cfg["system_salt"] = custom_salt_val
        cfg["kdf_info_pattern"] = self.input_info_pattern.text().strip()

        cfg["file01_enabled"] = self.chk_f01_en.isChecked()
        cfg["file01_comm_mode"] = self.combo_f01_comm.currentData()
        cfg["file01_read"] = self.combo_f01_read.currentData()
        cfg["file01_write"] = self.combo_f01_write.currentData()
        cfg["file01_change"] = self.combo_f01_change.currentData()

        cfg["file02_sdm"] = self.chk_f02_sdm.isChecked()
        cfg["file02_comm_mode"] = self.combo_f02_comm.currentData()
        cfg["file02_read"] = self.combo_f02_read.currentData()
        cfg["file02_write"] = self.combo_f02_write.currentData()
        cfg["file02_change"] = self.combo_f02_change.currentData()
        cfg["sdm_mac_key"] = self.combo_mac_key.currentData()
        cfg["file02_meta_key"] = self.combo_f02_meta.currentData()
        cfg["file02_ctr_ret_key"] = self.combo_f02_ctr_ret.currentData()
        cfg["enable_uid_mirror"] = self.chk_uid_mirror.isChecked()
        cfg["enable_ctr_mirror"] = self.chk_ctr_mirror.isChecked()

        cfg["file03_enabled"] = self.chk_f03_en.isChecked()
        cfg["file03_comm_mode"] = self.combo_f03_comm.currentData()
        cfg["file03_read"] = self.combo_f03_read.currentData()
        cfg["file03_write"] = self.combo_f03_write.currentData()
        cfg["file03_change"] = self.combo_f03_change.currentData()

        return cfg

    def save_and_apply(self):
        new_cfg = self.get_values_from_ui()
        if new_cfg is None:
            return
        self.config = new_cfg
        self.accept()

    def export_recipe(self):
        new_cfg = self.get_values_from_ui()
        if new_cfg is None:
            return

        raw_name = new_cfg["recipe_name"]
        safe_name = re.sub(r'[\\/*?:"<>| ]', '_', raw_name)
        default_filename = f"{safe_name}.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出配方文件 (JSON)",
            default_filename,
            "JSON 配方文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            recipe_data = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0",
                **new_cfg
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(recipe_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "导出成功", f"配方已成功导出至:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"无法写入配方文件:\n{e}")

    def import_recipe(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入配方文件 (JSON)",
            "",
            "JSON 配方文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("文件内容必须是 JSON 对象")

            if "config" in data and isinstance(data["config"], dict):
                data = {**data, **data["config"]}

            for k in DEFAULT_CONFIG.keys():
                if k in data:
                    self.config[k] = data[k]

            if "system_salt" in data and "kdf_custom_salt" not in data:
                self.config["kdf_custom_salt"] = data["system_salt"]

            if "recipe_name" not in data:
                # Use file basename if recipe_name missing
                base_n = os.path.splitext(os.path.basename(file_path))[0]
                self.config["recipe_name"] = base_n

            self.load_values_to_ui()
            QMessageBox.information(self, "导入成功", f"已成功加载配方文件:\n{os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析配方文件:\n{e}")


# ==============================================================================
# 虚拟表格模型与过滤器 (Model / View 架构)
# ==============================================================================
class RecordTableModel(QAbstractTableModel):
    """
    高性能虚拟表格数据模型，零多余控件开销，支持万级记录流畅渲染。
    """
    COLUMNS = [
        "时间",
        "卡片 UID",
        "作业类型",
        "状态",
        "主控 Key 0",
        "SDM 签名 Key",
        "NDEF 数据 / 模板",
        "耗时",
        "详细说明",
    ]

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self._records: List[Dict[str, Any]] = records if records is not None else []
        self._font_mono = QFont("Menlo", 9)
        self._font_mono.setStyleHint(QFont.Monospace)
        self._font_bold = QFont("Arial", 9, QFont.Bold)
        self._color_success = QColor("#166534")
        self._color_fail = QColor("#DC2626")
        self._color_text = QColor("#1E293B")

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None

        rec = self._records[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return rec.get("timestamp", "")
            elif col == 1:
                return rec.get("uid", "")
            elif col == 2:
                return rec.get("operation", "")
            elif col == 3:
                return "成功" if rec.get("status") == "SUCCESS" else "失败"
            elif col == 4:
                return rec.get("key0", "")
            elif col == 5:
                return rec.get("key_mac", "") or rec.get("key2_mac", "")
            elif col == 6:
                return rec.get("ndef_url", "")
            elif col == 7:
                return f"{rec.get('duration_ms', 0)} ms"
            elif col == 8:
                return rec.get("details", "")

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 3:
                return self._color_success if rec.get("status") == "SUCCESS" else self._color_fail
            elif col in (1, 4, 5):
                return self._color_text

        elif role == Qt.ItemDataRole.FontRole:
            if col in (1, 4, 5, 7):
                return self._font_mono
            elif col == 3:
                return self._font_bold

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 2, 3, 7):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 4:
                return rec.get("key0", "")
            elif col == 5:
                return rec.get("key_mac", "") or rec.get("key2_mac", "")
            elif col == 6:
                return rec.get("ndef_url", "")
            elif col == 8:
                return rec.get("details", "")

        elif role == Qt.ItemDataRole.UserRole:
            if col == 7:
                return rec.get("duration_ms", 0)
            elif col == 0:
                return rec.get("timestamp", "")

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def add_record(self, record: Dict[str, Any]):
        row = len(self._records)
        self.beginInsertRows(QModelIndex(), row, row)
        self._records.append(record)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._records.clear()
        self.endResetModel()

    def get_records(self) -> List[Dict[str, Any]]:
        return self._records


class RecordFilterProxyModel(QSortFilterProxyModel):
    """
    高性能即时搜索与状态过滤代理模型，支持全文字段匹配与数值列智能排序。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._keyword = ""
        self._status_filter = "ALL"  # "ALL", "SUCCESS", "FAIL"

    def set_keyword(self, text: str):
        self._keyword = text.strip().lower()
        self.invalidate()

    def set_status_filter(self, status: str):
        self._status_filter = status
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not model or not hasattr(model, "_records"):
            return True

        if not (0 <= source_row < len(model._records)):
            return False

        rec = model._records[source_row]

        # 1. 状态筛选
        rec_status = rec.get("status", "")
        if self._status_filter == "SUCCESS" and rec_status != "SUCCESS":
            return False
        elif self._status_filter == "FAIL" and rec_status == "SUCCESS":
            return False

        # 2. 关键词全文字段检索 (UID, URL, 说明, Key0)
        if self._keyword:
            uid = rec.get("uid", "").lower()
            url = rec.get("ndef_url", "").lower()
            details = rec.get("details", "").lower()
            key0 = rec.get("key0", "").lower()
            if (self._keyword not in uid and
                self._keyword not in url and
                self._keyword not in details and
                self._keyword not in key0):
                return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        col = left.column()
        if col == 7:  # 耗时按整数数值大小排序，非字符串字典序
            left_val = self.sourceModel().data(left, Qt.ItemDataRole.UserRole) or 0
            right_val = self.sourceModel().data(right, Qt.ItemDataRole.UserRole) or 0
            return left_val < right_val
        return super().lessThan(left, right)


# ==============================================================================
# 在线更新检测线程与关于弹窗
# ==============================================================================
APP_VERSION = "v1.0.3"
APP_GITHUB_REPO = "bestqiu-w/ntag424-dna-provisioner"


class UpdateCheckThread(QThread):
    check_finished = Signal(bool, str, str, str)  # has_update, latest_tag, release_notes, download_url
    check_error = Signal(str)

    def run(self):
        import urllib.request
        import json
        url = f"https://api.github.com/repos/{APP_GITHUB_REPO}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NTAG424-Provisioner-App"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    latest_tag = data.get("tag_name", "").strip()
                    release_notes = data.get("body", "").strip()
                    html_url = data.get("html_url", f"https://github.com/{APP_GITHUB_REPO}/releases")

                    has_update = bool(latest_tag and latest_tag != APP_VERSION)
                    self.check_finished.emit(has_update, latest_tag, release_notes, html_url)
                    return
            self.check_error.emit("服务器返回了未预期的 HTTP 状态码")
        except Exception as e:
            self.check_error.emit(str(e))


class UpdateDialog(QDialog):
    """新版本升级提醒弹窗。"""
    def __init__(self, latest_tag: str, release_notes: str, download_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("发现软件新版本")
        self.resize(520, 360)
        self.download_url = download_url

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"🎉 发现新版本: {latest_tag} (当前版本: {APP_VERSION})")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setStyleSheet("color: #2563EB;")
        layout.addWidget(title)

        lbl_notes = QLabel("更新日志与发行说明:")
        lbl_notes.setStyleSheet("font-weight: bold; color: #475569;")
        layout.addWidget(lbl_notes)

        txt_notes = QTextEdit()
        txt_notes.setReadOnly(True)
        txt_notes.setText(release_notes or "(本次发行暂无详细说明日志)")
        txt_notes.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 6px; font-size: 11px;")
        layout.addWidget(txt_notes)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_ignore = QPushButton("稍后再说")
        btn_ignore.setStyleSheet("background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 6px 14px; font-size: 11px;")
        btn_ignore.clicked.connect(self.reject)
        btn_box.addWidget(btn_ignore)

        btn_download = QPushButton("立即前往下载")
        btn_download.setStyleSheet("background-color: #2563EB; color: white; border: none; border-radius: 4px; padding: 6px 18px; font-size: 11px; font-weight: bold;")
        btn_download.clicked.connect(self._open_download)
        btn_box.addWidget(btn_download)

        layout.addLayout(btn_box)

    def _open_download(self):
        QDesktopServices.openUrl(QUrl(self.download_url))
        self.accept()


class AboutDialog(QDialog):
    """关于本软件对话框。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 NTAG 424 DNA 标签发卡与运维工具")
        self.resize(500, 320)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(14)

        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "assets", "icon.png")
        lbl_logo = QLabel()
        if os.path.exists(icon_path):
            pix = QIcon(icon_path).pixmap(56, 56)
            lbl_logo.setPixmap(pix)
        top_layout.addWidget(lbl_logo)

        v_head = QVBoxLayout()
        lbl_name = QLabel("NTAG424 Pro")
        lbl_name.setFont(QFont("Arial", 13, QFont.Bold))
        lbl_name.setStyleSheet("color: #0F172A;")
        v_head.addWidget(lbl_name)

        lbl_ver = QLabel(f"版本: {APP_VERSION}  |  NTAG 424 DNA 发卡与运维")
        lbl_ver.setStyleSheet("color: #64748B; font-size: 11px;")
        v_head.addWidget(lbl_ver)
        top_layout.addLayout(v_head)
        top_layout.addStretch()

        layout.addLayout(top_layout)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(div)

        desc = QLabel(
            "基于 Python 3 与 PySide6 打造的高性能轻量桌面工具，专用于 NXP NTAG 424 DNA "
            "防伪巡检标签的密钥注入、SUN / SDM 动态签名配置、出厂重置与诊断回读。\n\n"
            "• 支持 ACS ACR122U 等标准 PC/SC 读写器\n"
            "• 支持 HKDF-SHA256 与 AES-128-CMAC 双密码派生体系\n"
            "• 原生支持 NDEF Multi-Record (URI + Android AAR) 复合注入"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #334155; font-size: 11px; line-height: 1.4;")
        layout.addWidget(desc)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_repo = QPushButton("访问 GitHub 仓库")
        btn_repo.setStyleSheet("background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 4px; padding: 4px 12px; font-size: 11px;")
        btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{APP_GITHUB_REPO}")))
        btn_box.addWidget(btn_repo)
        btn_box.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background-color: #2563EB; color: white; border: none; border-radius: 4px; padding: 4px 18px; font-size: 11px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)


# ==============================================================================
# UI 图标生成工具 (轻量无外部依赖矢量渲染)
# ==============================================================================
def make_search_icon(color_hex: str = "#64748B", size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(3, 3, 7, 7)
    painter.drawLine(9, 9, 13, 13)
    painter.end()
    return QIcon(pix)


def ensure_chevron_icon(base_dir: str) -> str:
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    chevron_path = os.path.join(assets_dir, "chevron_down.png")
    if not os.path.exists(chevron_path):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#64748B"), 3.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(8.0, 13.0), QPointF(16.0, 20.0))
        p.drawLine(QPointF(16.0, 20.0), QPointF(24.0, 13.0))
        p.end()
        pix.save(chevron_path)
    return chevron_path.replace("\\", "/")


def ensure_check_icon(base_dir: str) -> str:
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    check_path = os.path.join(assets_dir, "check_white.png")
    if not os.path.exists(check_path):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#FFFFFF"), 3.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(7.5, 16.0), QPointF(13.0, 22.0))
        p.drawLine(QPointF(13.0, 22.0), QPointF(24.5, 9.5))
        p.end()
        pix.save(check_path)
    return check_path.replace("\\", "/")


def make_export_icon(color_hex: str = "#1D4ED8", size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(3, 11, 3, 13)
    painter.drawLine(3, 13, 13, 13)
    painter.drawLine(13, 13, 13, 11)
    painter.drawLine(8, 3, 8, 10)
    painter.drawLine(5, 7, 8, 10)
    painter.drawLine(11, 7, 8, 10)
    painter.end()
    return QIcon(pix)


def make_clear_icon(color_hex: str = "#64748B", size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color_hex), 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(3, 5, 13, 5)
    painter.drawLine(5, 5, 5, 13)
    painter.drawLine(11, 5, 11, 13)
    painter.drawLine(5, 13, 11, 13)
    painter.drawLine(7, 7, 7, 11)
    painter.drawLine(9, 7, 9, 11)
    painter.drawLine(6, 3, 10, 3)
    painter.end()
    return QIcon(pix)


# ==============================================================================
# 主窗口 (MainWindow)
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NTAG424 Pro")
        self.resize(1120, 880)
        self.setMinimumSize(980, 750)

        # Set Window Icon
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.config = load_config()
        if not self.config.get("recipe_name"):
            self.config["recipe_name"] = generate_random_recipe_name()

        self.records: List[Dict[str, Any]] = []
        self.table_model = RecordTableModel(self.records, self)
        self.proxy_model = RecordFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.update_checker_thread: Optional[UpdateCheckThread] = None

        self.current_card_uid: Optional[str] = None
        self.is_reader_connected: bool = False

        self.worker = NFCWorker()
        self.worker.reader_status.connect(self.on_reader_status)
        self.worker.card_detected.connect(self.on_card_detected)
        self.worker.card_removed.connect(self.on_card_removed)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.log_message.connect(self.append_log)
        self.worker.tag_processed.connect(self.on_tag_processed)
        self.worker.single_action_started.connect(self.on_single_action_started)
        self.worker.single_action_finished.connect(self.on_single_action_finished)

        self.setup_ui()
        self.setup_menu_bar()
        self.update_recipe_banner()
        self.sync_worker_config()
        self.center_on_top_screen()

        # Start background polling worker
        self.worker.start()

    def center_on_top_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = self.width()
            h = min(self.height(), geo.height() - 40)
            if h != self.height():
                self.resize(w, h)
            x = geo.x() + max(0, (geo.width() - w) // 2)
            y = geo.y() + max(20, int((geo.height() - h) * 0.22))
            self.move(x, y)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 10, 12, 10)

        # ---------------------------------------------------------
        # 1. Top Header Bar (Title + Reader Connection Badge)
        # ---------------------------------------------------------
        header_bar = QFrame()
        header_bar.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(12)

        title_label = QLabel("NTAG424 Pro")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setStyleSheet("color: #0F172A; border: none;")
        h_layout.addWidget(title_label)

        sub_label = QLabel("DNA 标签发卡与运维")
        sub_label.setStyleSheet("color: #64748B; font-size: 11px; border: none; padding-top: 3px;")
        h_layout.addWidget(sub_label)

        h_layout.addStretch()

        # Reader status indicator on the top right
        self.reader_status_label = QLabel("○ 正在检测读卡器...")
        self.reader_status_label.setStyleSheet("""
            color: #64748B;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            border: none;
            padding: 2px 4px;
        """)
        h_layout.addWidget(self.reader_status_label)

        main_layout.addWidget(header_bar)

        # ---------------------------------------------------------
        # 2. Main Navigation Tabs (平级: 生产作业台 vs 硬件设备管理)
        # ---------------------------------------------------------
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet("""
            QTabBar::tab {
                font-size: 13px;
                font-weight: bold;
                padding: 8px 24px;
                min-width: 140px;
                color: #475569;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                border-bottom: 2px solid #2563EB;
                color: #2563EB;
            }
        """)

        # Tab 1: 生产作业台 (默认工作主页)
        tab_workstation = QWidget()
        self.setup_workstation_tab(tab_workstation)
        self.main_tabs.addTab(tab_workstation, "生产作业台")

        # Tab 2: 硬件设备管理 (系统基础设施，与作业台平级)
        tab_hardware = QWidget()
        self.setup_hardware_tab(tab_hardware)
        self.main_tabs.addTab(tab_hardware, "硬件设备管理")

        main_layout.addWidget(self.main_tabs)

    def setup_workstation_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---------------------------------------------------------
        # A. Current Active Recipe Banner (带【概览】与【调整】入口)
        # ---------------------------------------------------------
        recipe_banner = QFrame()
        recipe_banner.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
        """)
        rb_layout = QHBoxLayout(recipe_banner)
        rb_layout.setContentsMargins(12, 6, 12, 6)
        rb_layout.setSpacing(10)

        self.lbl_recipe_title = QLabel("当前配方: Default_Patrol")
        self.lbl_recipe_title.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_recipe_title.setStyleSheet("color: #1E293B; border: none;")
        rb_layout.addWidget(self.lbl_recipe_title)

        rb_layout.addStretch()

        # Recipe Summary / Peek Button
        btn_peek_recipe = QPushButton("配方概览")
        btn_peek_recipe.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #F1F5F9; border-color: #94A3B8; }
        """)
        btn_peek_recipe.clicked.connect(self.show_recipe_summary_dialog)
        rb_layout.addWidget(btn_peek_recipe)

        # Recipe Edit Button
        btn_edit_recipe = QPushButton("调整配方")
        btn_edit_recipe.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        btn_edit_recipe.clicked.connect(self.open_recipe_edit_dialog)
        rb_layout.addWidget(btn_edit_recipe)

        layout.addWidget(recipe_banner)

        # ---------------------------------------------------------
        # B. Operation Center Card (Mode Switch + Card Sensor Badge + Action Area)
        # ---------------------------------------------------------
        self.ctrl_card = QFrame()
        self.ctrl_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
        """)
        ctrl_layout = QVBoxLayout(self.ctrl_card)
        ctrl_layout.setContentsMargins(12, 10, 12, 10)
        ctrl_layout.setSpacing(8)

        # Line 1: Mode Switch & Live Card Sensor Indicator
        mode_line = QHBoxLayout()
        mode_line.setSpacing(12)

        lbl_mode_caption = QLabel("作业模式:")
        lbl_mode_caption.setStyleSheet("font-weight: bold; color: #1E293B; border: none;")
        mode_line.addWidget(lbl_mode_caption)

        self.group_work_mode = QButtonGroup(self)
        self.radio_mode_single = QRadioButton("单卡调试模式")
        self.radio_mode_batch = QRadioButton("批量自动模式")
        self.radio_mode_single.setChecked(True)
        self.radio_mode_single.setStyleSheet("font-weight: bold; color: #0F766E; border: none;")
        self.radio_mode_batch.setStyleSheet("font-weight: bold; color: #C2410C; border: none;")

        self.group_work_mode.addButton(self.radio_mode_single, 0)
        self.group_work_mode.addButton(self.radio_mode_batch, 1)
        self.group_work_mode.buttonClicked.connect(self.on_work_mode_switched)

        mode_line.addWidget(self.radio_mode_single)
        mode_line.addWidget(self.radio_mode_batch)
        mode_line.addStretch()

        # Real-time Card Status Indicator (Clean Industrial Style)
        self.lbl_card_status = QLabel("<span style='color:#94A3B8;'>○</span> <span style='color:#64748B;'>待放置卡片</span>")
        self.lbl_card_status.setStyleSheet("""
            background: transparent;
            border: none;
            font-size: 12px;
            padding: 2px 4px;
        """)
        mode_line.addWidget(self.lbl_card_status)
        ctrl_layout.addLayout(mode_line)

        # Divider line
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #F1F5F9;")
        ctrl_layout.addWidget(div)

        # Line 2: Stacked Action Controls (Single vs Batch)
        self.stack_operations = QStackedWidget()

        # Page 0: Single Mode Actions
        page_single = QWidget()
        l_single = QVBoxLayout(page_single)
        l_single.setContentsMargins(0, 0, 0, 0)
        l_single.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_base_qss = """
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 16px;
                min-height: 20px;
            }
            QPushButton:disabled {
                background-color: #F1F5F9 !important;
                color: #94A3B8 !important;
                border: 1px solid #E2E8F0 !important;
            }
        """

        self.btn_single_provision = QPushButton("发卡注入")
        self.btn_single_provision.setStyleSheet(btn_base_qss + "QPushButton:enabled { background-color: #2563EB; color: white; border: none; } QPushButton:enabled:hover { background-color: #1D4ED8; }")
        self.btn_single_provision.clicked.connect(lambda: self.on_single_action_clicked("provision"))
        self.btn_single_provision.setEnabled(False)
        btn_row.addWidget(self.btn_single_provision)

        self.btn_single_restore = QPushButton("恢复出厂")
        self.btn_single_restore.setStyleSheet(btn_base_qss + "QPushButton:enabled { background-color: #DC2626; color: white; border: none; } QPushButton:enabled:hover { background-color: #B91C1C; }")
        self.btn_single_restore.clicked.connect(lambda: self.on_single_action_clicked("restore"))
        self.btn_single_restore.setEnabled(False)
        btn_row.addWidget(self.btn_single_restore)

        self.btn_single_inspect = QPushButton("读取诊断")
        self.btn_single_inspect.setStyleSheet(btn_base_qss + "QPushButton:enabled { background-color: #0D9488; color: white; border: none; } QPushButton:enabled:hover { background-color: #0F766E; }")
        self.btn_single_inspect.clicked.connect(lambda: self.on_single_action_clicked("inspect"))
        self.btn_single_inspect.setEnabled(False)
        btn_row.addWidget(self.btn_single_inspect)

        l_single.addLayout(btn_row)

        # Single Card Result Card
        self.lbl_single_result = QLabel("执行结果: 就绪 | 将标签置于读卡区后点击上方按钮执行")
        self.lbl_single_result.setStyleSheet("""
            color: #475569;
            font-family: Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            background: #F8FAFC;
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #E2E8F0;
        """)
        self.lbl_single_result.setWordWrap(True)
        l_single.addWidget(self.lbl_single_result)

        self.stack_operations.addWidget(page_single)

        # Page 1: Batch Mode Actions
        page_batch = QWidget()
        l_batch = QVBoxLayout(page_batch)
        l_batch.setContentsMargins(0, 0, 0, 0)
        l_batch.setSpacing(6)

        # Batch Control Row
        b_ctrl_row = QHBoxLayout()
        b_ctrl_row.setSpacing(12)

        lbl_b_act = QLabel("流水线动作:")
        lbl_b_act.setStyleSheet("font-weight: bold; color: #1E293B; border: none;")
        b_ctrl_row.addWidget(lbl_b_act)

        self.group_batch_action = QButtonGroup(self)
        self.radio_batch_prov = QRadioButton("批量发卡注入")
        self.radio_batch_rest = QRadioButton("批量恢复出厂")
        self.radio_batch_prov.setChecked(True)
        self.radio_batch_prov.setStyleSheet("font-weight: bold; color: #2563EB; border: none;")
        self.radio_batch_rest.setStyleSheet("font-weight: bold; color: #DC2626; border: none;")
        self.group_batch_action.addButton(self.radio_batch_prov, 0)
        self.group_batch_action.addButton(self.radio_batch_rest, 1)
        self.group_batch_action.buttonClicked.connect(self.on_batch_action_switched)
        b_ctrl_row.addWidget(self.radio_batch_prov)
        b_ctrl_row.addWidget(self.radio_batch_rest)

        b_ctrl_row.addStretch()

        self.btn_batch_toggle = QPushButton("启动批量作业")
        self.btn_batch_toggle.setFixedHeight(32)
        self.btn_batch_toggle.setFixedWidth(140)
        self.btn_batch_toggle.setFont(QFont("Arial", 11, QFont.Bold))
        self.btn_batch_toggle.setStyleSheet("""
            QPushButton {
                background-color: #16A34A;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #15803D; }
        """)
        self.btn_batch_toggle.clicked.connect(self.toggle_batch_running)
        b_ctrl_row.addWidget(self.btn_batch_toggle)
        l_batch.addLayout(b_ctrl_row)

        # Batch Stats Row (Clean Industrial Metrics)
        self.lbl_batch_stats = QLabel("已处理: 0 张  |  成功: 0  |  失败: 0")
        self.lbl_batch_stats.setStyleSheet("""
            color: #475569;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            border: none;
            padding: 2px 0px;
        """)
        l_batch.addWidget(self.lbl_batch_stats)

        self.stack_operations.addWidget(page_batch)
        ctrl_layout.addWidget(self.stack_operations)

        layout.addWidget(self.ctrl_card)

        # ---------------------------------------------------------
        # C. Splitter: Operation History Table & Realtime Logs
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Vertical)

        # Top: Table Widget
        table_container = QWidget()
        t_layout = QVBoxLayout(table_container)
        t_layout.setContentsMargins(0, 2, 0, 0)
        t_layout.setSpacing(0)

        # 1. 现代化表格工具栏面板 (统一卡片外观 + 矢量图标 + 状态指示徽标)
        table_toolbar = QFrame()
        table_toolbar.setObjectName("table_toolbar")
        table_toolbar.setStyleSheet("""
            QFrame#table_toolbar {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-bottom: 1px solid #E2E8F0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 4px 6px;
            }
        """)
        t_head_layout = QHBoxLayout(table_toolbar)
        t_head_layout.setContentsMargins(6, 4, 6, 4)
        t_head_layout.setSpacing(8)

        lbl_table = QLabel("作业执行记录")
        lbl_table.setFont(QFont("Arial", 11, QFont.Bold))
        lbl_table.setStyleSheet("color: #1E293B; border: none; background: transparent;")
        t_head_layout.addWidget(lbl_table)

        # 动态筛选与匹配指示徽章
        self.lbl_table_badge = QLabel("共 0 条")
        self.lbl_table_badge.setStyleSheet("""
            QLabel {
                background-color: #E2E8F0;
                color: #475569;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 9px;
                border: 1px solid #CBD5E1;
            }
        """)
        t_head_layout.addWidget(self.lbl_table_badge)

        t_head_layout.addStretch()

        # 实时全字段检索输入框 (带矢量放大镜图标与一键清空)
        self.input_table_search = QLineEdit()
        self.input_table_search.setObjectName("table_search_input")
        self.input_table_search.setPlaceholderText("检索 UID / 链接 / 密钥 / 备注...")
        self.input_table_search.setClearButtonEnabled(True)
        self.input_table_search.setFixedWidth(225)
        self.input_table_search.setFixedHeight(26)
        self.input_table_search.addAction(make_search_icon("#64748B"), QLineEdit.ActionPosition.LeadingPosition)
        self.input_table_search.setStyleSheet("""
            QLineEdit#table_search_input {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 5px;
                padding: 2px 6px;
                font-size: 11px;
                color: #1E293B;
            }
            QLineEdit#table_search_input:hover {
                border-color: #94A3B8;
            }
            QLineEdit#table_search_input:focus {
                border-color: #2563EB;
                background-color: #FFFFFF;
            }
        """)
        self.input_table_search.textChanged.connect(self.on_table_search_changed)
        t_head_layout.addWidget(self.input_table_search)

        # 状态筛选下拉框 (简洁纯文字 + 现代矢量微箭头)
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        chevron_path = ensure_chevron_icon(base_dir)

        self.combo_table_status = QComboBox()
        self.combo_table_status.setObjectName("table_status_combo")
        self.combo_table_status.addItem("全部状态", "ALL")
        self.combo_table_status.addItem("仅看成功", "SUCCESS")
        self.combo_table_status.addItem("仅看失败", "FAIL")
        self.combo_table_status.setFixedWidth(102)
        self.combo_table_status.setFixedHeight(26)
        self.combo_table_status.setStyleSheet(f"""
            QComboBox#table_status_combo {{
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 5px;
                padding: 2px 20px 2px 8px;
                font-size: 11px;
                color: #334155;
                font-weight: 500;
            }}
            QComboBox#table_status_combo:hover {{
                border-color: #94A3B8;
            }}
            QComboBox#table_status_combo:focus {{
                border-color: #2563EB;
            }}
            QComboBox#table_status_combo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: none;
            }}
            QComboBox#table_status_combo::down-arrow {{
                image: url("{chevron_path}");
                width: 9px;
                height: 9px;
                margin-right: 6px;
            }}
            QComboBox#table_status_combo QAbstractItemView {{
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                selection-background-color: #EFF6FF;
                selection-color: #1D4ED8;
                padding: 4px;
                outline: none;
            }}
        """)
        self.combo_table_status.currentIndexChanged.connect(self.on_table_status_filter_changed)
        t_head_layout.addWidget(self.combo_table_status)

        # 导出 CSV 按钮 (带矢量下载图标)
        btn_export = QPushButton("导出 CSV")
        btn_export.setFixedHeight(26)
        btn_export.setIcon(make_export_icon("#1D4ED8"))
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px solid #BFDBFE;
                border-radius: 5px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #DBEAFE;
                border-color: #93C5FD;
            }
            QPushButton:pressed {
                background-color: #BFDBFE;
            }
        """)
        btn_export.clicked.connect(self.export_records)
        t_head_layout.addWidget(btn_export)

        # 清空记录按钮 (带矢量废纸篓图标)
        btn_clear = QPushButton("清空")
        btn_clear.setFixedHeight(26)
        btn_clear.setIcon(make_clear_icon("#64748B"))
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #64748B;
                border: 1px solid #CBD5E1;
                border-radius: 5px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #FEF2F2;
                color: #DC2626;
                border-color: #FECACA;
            }
            QPushButton:pressed {
                background-color: #FEE2E2;
            }
        """)
        btn_clear.clicked.connect(self.clear_records)
        t_head_layout.addWidget(btn_clear)

        t_layout.addWidget(table_toolbar)

        # 2. 高性能虚拟视口表格 (QTableView + ProxyModel)
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)

        # 细粒度工业列宽配置
        header.resizeSection(0, 135)  # 时间 (YYYY-MM-DD HH:MM:SS)
        header.resizeSection(1, 125)  # 卡片 UID (14 Hex)
        header.resizeSection(2, 75)   # 作业类型
        header.resizeSection(3, 55)   # 状态 (成功/失败)
        header.resizeSection(4, 175)  # 主控 Key 0 (32 Hex)
        header.resizeSection(5, 175)  # SDM 签名 Key (32 Hex)
        header.setSectionResizeMode(6, QHeaderView.Stretch)  # NDEF 数据 / 模板 (自适应填满)
        header.resizeSection(7, 65)   # 耗时
        header.resizeSection(8, 160)  # 详细说明

        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setStyleSheet("""
            QTableView {
                border: 1px solid #CBD5E1;
                border-top: none;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                background-color: #FFFFFF;
                gridline-color: #F1F5F9;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #475569;
                font-weight: bold;
                border: none;
                border-right: 1px solid #E2E8F0;
                border-bottom: 1px solid #CBD5E1;
                padding: 5px 6px;
            }
        """)
        t_layout.addWidget(self.table)
        splitter.addWidget(table_container)

        # Bottom: Diagnostic Log Console
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 2, 0, 0)
        log_layout.setSpacing(4)

        log_head = QHBoxLayout()
        lbl_log = QLabel("通信与诊断日志")
        lbl_log.setStyleSheet("font-weight: bold; font-size: 11px; color: #475569;")
        log_head.addWidget(lbl_log)
        log_head.addStretch()

        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.setFixedHeight(24)
        btn_clear_log.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #64748B;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #F8FAFC; }
        """)
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_head.addWidget(btn_clear_log)
        log_layout.addLayout(log_head)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("""
            background-color: #0F172A;
            color: #E2E8F0;
            font-family: Menlo, Monaco, Consolas, 'Courier New', monospace;
            font-size: 11px;
            border-radius: 4px;
            border: 1px solid #1E293B;
            padding: 6px;
        """)
        log_layout.addWidget(self.txt_log)
        splitter.addWidget(log_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    def setup_hardware_tab(self, parent: QWidget):
        """读卡器与硬件管理界面（与发卡作业台平级的主标签页）。"""
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. Reader Hardware Status Card
        grp_hw_stat = QGroupBox("读卡器连接状态")
        grp_hw_stat.setStyleSheet("QGroupBox { border: 1px solid #CBD5E1; border-radius: 6px; font-weight: bold; margin-top: 6px; padding-top: 10px; }")
        grid_hw = QGridLayout(grp_hw_stat)
        grid_hw.setSpacing(8)

        grid_hw.addWidget(QLabel("识别到的物理读卡器:"), 0, 0)
        self.lbl_hw_device = QLabel("正在扫描系统 PC/SC 接口...")
        self.lbl_hw_device.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_hw_device.setStyleSheet("color: #475569;")
        grid_hw.addWidget(self.lbl_hw_device, 0, 1)

        btn_refresh_reader = QPushButton("重新扫描读卡器")
        btn_refresh_reader.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #F1F5F9; border-color: #94A3B8; }
        """)
        btn_refresh_reader.clicked.connect(self.on_refresh_reader_clicked)
        grid_hw.addWidget(btn_refresh_reader, 0, 2)

        grid_hw.addWidget(QLabel("底层硬件驱动接口:"), 1, 0)
        lbl_protocol_info = QLabel("PC/SC (Personal Computer/Smart Card) 标准规范 (WinSCard / SmartCardServices)")
        lbl_protocol_info.setStyleSheet("color: #64748B; font-size: 11px;")
        grid_hw.addWidget(lbl_protocol_info, 1, 1, 1, 2)

        layout.addWidget(grp_hw_stat)

        # 2. Sound & Light Feedback Settings
        grp_feedback = QGroupBox("读卡器声光反馈选项")
        grp_feedback.setStyleSheet("QGroupBox { border: 1px solid #CBD5E1; border-radius: 6px; font-weight: bold; margin-top: 6px; padding-top: 10px; }")
        grid_fb = QGridLayout(grp_feedback)
        grid_fb.setSpacing(10)

        self.chk_buzzer = QCheckBox("启用 ACR122U 蜂鸣器与 LED 声光反馈")
        self.chk_buzzer.setChecked(self.config.get("auto_buzzer", True))
        self.chk_buzzer.stateChanged.connect(self.on_buzzer_setting_changed)
        grid_fb.addWidget(self.chk_buzzer, 0, 0)

        lbl_fb_desc = QLabel("说明: 开启后，发卡或诊断成功将触发读卡器短鸣与绿灯，失败时长鸣与红灯；若需要完全静音作业，取消勾选即可。")
        lbl_fb_desc.setStyleSheet("color: #64748B; font-size: 11px;")
        grid_fb.addWidget(lbl_fb_desc, 1, 0)

        layout.addWidget(grp_feedback)

        # 3. Environment & PC/SC Diagnostic Guide
        grp_guide = QGroupBox("驱动与运行环境指引")
        grp_guide.setStyleSheet("QGroupBox { border: 1px solid #CBD5E1; border-radius: 6px; font-weight: bold; margin-top: 6px; padding-top: 10px; }")
        l_guide = QVBoxLayout(grp_guide)
        l_guide.setSpacing(6)

        guide_text = QLabel(
            "• macOS 用户: 本系统通过 macOS 原生 PC/SC (SmartCardServices) 直接通信，无需安装繁琐第三方驱动。\n"
            "• Windows 用户: 请确保已安装 ACS 官方 ACR122U USB 驱动，智能卡系统服务 (Smart Card Service) 处于运行状态。\n"
            "• Linux 用户: 需预先安装 pcscd 及 libpcsclite，并启动 pcscd 服务守护进程。\n"
            "• 遇读卡器无响应: 可拔出 USB 重新插入，或点击上方【重新检测读卡器】刷新。"
        )
        guide_text.setStyleSheet("color: #475569; font-size: 11px; line-height: 1.5;")
        l_guide.addWidget(guide_text)

        layout.addWidget(grp_guide)
        layout.addStretch()

    # -------------------------------------------------------------
    # 配方管理交互 (弹窗概览与弹窗调整)
    # -------------------------------------------------------------
    def update_recipe_banner(self):
        name = self.config.get("recipe_name", "Default_Patrol")
        self.lbl_recipe_title.setText(f"当前配方: {name}")

    def show_recipe_summary_dialog(self):
        """弹出 Key-Value 简单概览弹窗。"""
        dlg = RecipeSummaryDialog(self.config, self)
        dlg.exec()
        if dlg.request_edit:
            self.open_recipe_edit_dialog()

    def open_recipe_edit_dialog(self):
        """打开配方编辑与管理弹窗。"""
        dlg = RecipeEditDialog(self.config, self)
        if dlg.exec() == QDialog.Accepted:
            self.config = dlg.config
            save_config(self.config)
            self.sync_worker_config()
            self.update_recipe_banner()
            self.append_log(f"[CONFIG] 配方已更新并应用: {self.config.get('recipe_name', '')} (算法: {self.config['kdf_algorithm']})")
            QMessageBox.information(self, "应用成功", f"配方【{self.config.get('recipe_name', '')}】已保存并立即生效！")

    def on_buzzer_setting_changed(self):
        self.config["auto_buzzer"] = self.chk_buzzer.isChecked()
        save_config(self.config)
        self.sync_worker_config()
        self.append_log(f"[CONFIG] 读卡器声光反馈已{'启用' if self.config['auto_buzzer'] else '关闭'}")

    def on_refresh_reader_clicked(self):
        self.append_log("[INFO] 正在主动扫描系统 PC/SC 读卡器设备...")
        try:
            from smartcard.System import readers
            all_r = readers()
            if all_r:
                r_names = [str(r) for r in all_r]
                self.append_log(f"[INFO] 系统枚举到 {len(r_names)} 个读卡器: {', '.join(r_names)}")
                found_name = self.worker.reader.find_reader()
                if found_name:
                    self.on_reader_status(True, f"已连接: {found_name}")
                    list_text = "\n".join([f"• {name}" for name in r_names])
                    QMessageBox.information(
                        self,
                        "扫描成功",
                        f"系统成功枚举到 {len(all_r)} 个硬件读卡器接口：\n\n{list_text}\n\n当前绑定: {found_name}"
                    )
                    return
            self.on_reader_status(False, "未检测到读卡器")
            self.append_log("[WARN] 扫描未发现可用的智能卡读卡器")
            QMessageBox.warning(
                self,
                "未发现设备",
                "系统当前未检测到任何插入的智能卡/NFC 读写器。\n\n请检查：\n1. ACR122U USB 线缆是否插紧；\n2. 电脑 USB 接口供电是否正常。"
            )
        except Exception as e:
            self.on_reader_status(False, "读卡器服务未就绪")
            self.append_log(f"[WARN] 扫描异常: {e}")
            QMessageBox.warning(self, "PC/SC 异常", f"无法枚举智能卡读卡器:\n\n{e}\n\n可能原因: 操作系统智能卡服务 (pcscd / Smart Card) 未启动。")

    def append_log(self, text: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        time_tag = f"<span style='color: #64748B;'>[{now_str}]</span>"
        indent_spaces = " " * 11  # Matches [HH:MM:SS] width in monospace font

        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            if not line:
                continue
            is_subline = line.startswith("  ") or line.startswith("\t") or line.strip().startswith("•")

            # Syntax colorize common log tags
            escaped = html.escape(line.strip())
            for tag, color in [
                ("[SUCCESS]", "#4ADE80"),
                ("[ERROR]", "#F87171"),
                ("[WARN]", "#FBBF24"),
                ("[INFO]", "#38BDF8"),
                ("[EXEC]", "#C084FC"),
                ("[CONFIG]", "#94A3B8"),
                ("[TEST]", "#A78BFA"),
            ]:
                if tag in escaped:
                    escaped = escaped.replace(tag, f"<b style='color: {color};'>{tag}</b>")
                    break

            if is_subline:
                formatted_lines.append(f"{indent_spaces} {escaped}")
            else:
                formatted_lines.append(f"{time_tag} {escaped}")

        html_block = f"<div style='white-space: pre-wrap; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; line-height: 140%;'>{'<br>'.join(formatted_lines)}</div>"

        self.txt_log.append(html_block)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def _update_single_buttons_state(self):
        can_operate = bool(self.is_reader_connected and self.current_card_uid)
        self.btn_single_provision.setEnabled(can_operate)
        self.btn_single_restore.setEnabled(can_operate)
        self.btn_single_inspect.setEnabled(can_operate)

    def on_work_mode_switched(self):
        is_single = self.radio_mode_single.isChecked()
        mode_str = "single" if is_single else "batch"
        self.stack_operations.setCurrentIndex(0 if is_single else 1)

        # Safety: Pause batch if running
        if is_single and self.worker.batch_running:
            self.worker.pause_batch()
            self.btn_batch_toggle.setText("启动批量作业")
            self.btn_batch_toggle.setStyleSheet("""
                QPushButton { background-color: #16A34A; color: white; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: #15803D; }
            """)

        self.worker.set_work_mode(mode_str)

        if is_single:
            if self.current_card_uid:
                self.lbl_card_status.setText(f"<span style='color:#16A34A;'>●</span> <span style='color:#0F172A; font-weight:600;'>卡片已就绪:</span> <span style='font-family: Menlo, Monaco, Consolas, monospace; font-weight:bold; color:#1E293B;'>{self.current_card_uid}</span>")
            else:
                self.lbl_card_status.setText("<span style='color:#94A3B8;'>○</span> <span style='color:#64748B;'>待放置卡片</span>")
            self._update_single_buttons_state()

    def on_batch_action_switched(self):
        is_prov = self.radio_batch_prov.isChecked()
        action_str = "provision" if is_prov else "restore"
        self.worker.set_batch_mode(action_str)

    def on_single_action_clicked(self, action: str):
        if not self.current_card_uid:
            QMessageBox.warning(self, "未感应到卡片", "读卡器感应区未检测到卡片，请先放置 NTAG 424 DNA 标签。")
            return
        self.worker.request_single_action(action)

    def on_single_action_started(self, action: str):
        self.btn_single_provision.setEnabled(False)
        self.btn_single_restore.setEnabled(False)
        self.btn_single_inspect.setEnabled(False)

        names = {
            "provision": "正在发卡...",
            "restore": "正在恢复出厂...",
            "inspect": "正在读取诊断...",
        }
        if action == "provision":
            self.btn_single_provision.setText(names["provision"])
        elif action == "restore":
            self.btn_single_restore.setText(names["restore"])
        elif action == "inspect":
            self.btn_single_inspect.setText(names["inspect"])

        self.lbl_single_result.setText("通信中: 正在与卡片交互，请保持卡片贴合读卡区...")
        self.lbl_single_result.setStyleSheet("color: #1D4ED8; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")

    def on_single_action_finished(self, action: str, success: bool, msg: str, detail: dict):
        self.btn_single_provision.setText("发卡注入")
        self.btn_single_restore.setText("恢复出厂")
        self.btn_single_inspect.setText("读取诊断")

        # Crucial Workflow Polish: If card is still on antenna, re-enable buttons so user can chain actions
        self._update_single_buttons_state()

        uid_str = detail.get("uid", self.current_card_uid or "未知")

        if action == "inspect":
            if success:
                auth_status = detail.get("auth_status", "")
                auth_d = detail.get("auth_desc", "")
                ndef_c = detail.get("ndef_content", "")
                card_k0 = detail.get("card_active_key0", "")
                card_km = detail.get("card_active_key_mac", "")
                recipe_k0 = detail.get("recipe_derived_key0", "")
                recipe_km = detail.get("recipe_derived_key_mac", "")
                mac_no = detail.get("mac_key_slot", 3)

                if auth_status == "FACTORY_DEFAULT":
                    ndef_display = "空白 (未写入数据)" if "(空白卡片" in ndef_c else f"{ndef_c} (出厂预制/历史残留)"
                    self.lbl_single_result.setText(
                        f"[读取诊断完成] UID: {uid_str}\n"
                        f"卡片状态: {auth_d}\n"
                        f"卡片当前 Key 0: 00000000000000000000000000000000 (出厂默认全0)\n"
                        f"NDEF 状态: {ndef_display}\n"
                        f"当前配方待注入: Key 0 ({recipe_k0}) | Key {mac_no} ({recipe_km})"
                    )
                elif auth_status == "MATCHED_MASTER":
                    self.lbl_single_result.setText(
                        f"[读取诊断完成] UID: {uid_str}\n"
                        f"卡片状态: {auth_d}\n"
                        f"生效 Key 0: {card_k0} | 生效 Key {mac_no} (MAC): {card_km}\n"
                        f"NDEF 记录: {ndef_c}"
                    )
                else:
                    self.lbl_single_result.setText(
                        f"[读取诊断完成] UID: {uid_str}\n"
                        f"卡片状态: {auth_d}\n"
                        f"卡片当前密钥: 芯片受硬件保护不可读 (与当前系统配方不匹配)\n"
                        f"NDEF 记录: {ndef_c}"
                    )
                self.lbl_single_result.setStyleSheet("color: #15803D; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")
            else:
                self.lbl_single_result.setText(f"[读取诊断失败] UID: {uid_str}\n原因: {msg}")
                self.lbl_single_result.setStyleSheet("color: #B91C1C; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")

        elif action == "provision":
            if success:
                algo = detail.get("kdf_algo", "")
                mac_no = detail.get("mac_key", 3)
                k0 = detail.get("derived_key0", "")
                km = detail.get("derived_key2_mac", "")
                sample = detail.get("read_sample", "")
                self.lbl_single_result.setText(
                    f"[发卡注入成功] UID: {uid_str} ({algo})\n"
                    f"Key 0: {k0} | Key {mac_no} (MAC): {km}\n"
                    f"回读校验: {sample}"
                )
                self.lbl_single_result.setStyleSheet("color: #15803D; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")
            else:
                self.lbl_single_result.setText(f"[发卡注入失败] UID: {uid_str}\n原因: {msg}")
                self.lbl_single_result.setStyleSheet("color: #B91C1C; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")

        elif action == "restore":
            if success:
                self.lbl_single_result.setText(
                    f"[恢复出厂成功] UID: {uid_str}\n"
                    f"卡片密钥已重置为出厂全 0 (00*16)，SDM 已关闭。"
                )
                self.lbl_single_result.setStyleSheet("color: #15803D; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")
            else:
                self.lbl_single_result.setText(f"[恢复出厂失败] UID: {uid_str}\n原因: {msg}")
                self.lbl_single_result.setStyleSheet("color: #B91C1C; font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px; background: #F8FAFC; padding: 8px 12px; border-radius: 4px; border: 1px solid #CBD5E1;")

    def on_card_detected(self, uid_hex: str):
        self.current_card_uid = uid_hex
        self.lbl_card_status.setText(f"<span style='color:#16A34A;'>●</span> <span style='color:#0F172A; font-weight:600;'>卡片已就绪:</span> <span style='font-family: Menlo, Monaco, Consolas, monospace; font-weight:bold; color:#1E293B;'>{uid_hex}</span>")
        self._update_single_buttons_state()

    def on_card_removed(self):
        self.current_card_uid = None
        self.lbl_card_status.setText("<span style='color:#94A3B8;'>○</span> <span style='color:#64748B;'>待放置卡片</span>")
        self._update_single_buttons_state()

        self.btn_single_provision.setText("发卡注入")
        self.btn_single_restore.setText("恢复出厂")
        self.btn_single_inspect.setText("读取诊断")

    def toggle_batch_running(self):
        if not self.worker.batch_running:
            m_hex = self.config.get("master_key", "").replace(" ", "").replace(":", "")
            if len(m_hex) != 32:
                QMessageBox.warning(self, "配方参数错误", "当前配方 Master Key 必须是 32 位十六进制字符，请点击【调整配方】修正。")
                return

            self.worker.start_batch()
            self.btn_batch_toggle.setText("暂停批量作业")
            self.btn_batch_toggle.setStyleSheet("""
                QPushButton { background-color: #EA580C; color: white; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: #C2410C; }
            """)
        else:
            self.worker.pause_batch()
            self.btn_batch_toggle.setText("启动批量作业")
            self.btn_batch_toggle.setStyleSheet("""
                QPushButton { background-color: #16A34A; color: white; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: #15803D; }
            """)

    def sync_worker_config(self):
        batch_act = "provision" if self.radio_batch_prov.isChecked() else "restore"
        self.worker.set_config(self.config, mode=batch_act)

    def on_reader_status(self, connected: bool, message: str):
        self.is_reader_connected = connected
        self.btn_batch_toggle.setEnabled(connected)
        self._update_single_buttons_state()

        if connected:
            self.reader_status_label.setText(f"<span style='color:#16A34A;'>●</span> <span style='color:#1E293B; font-weight:500;'>{message}</span>")
            self.lbl_hw_device.setText(f"● {message}")
            self.lbl_hw_device.setStyleSheet("color: #16A34A; font-weight: bold; background: transparent; border: none;")
        else:
            self.reader_status_label.setText(f"<span style='color:#DC2626;'>○</span> <span style='color:#991B1B;'>{message}</span>")
            self.lbl_hw_device.setText("○ 未检测到读卡器 (请插入 USB)")
            self.lbl_hw_device.setStyleSheet("color: #DC2626; font-weight: bold; background: transparent; border: none;")
            self.lbl_card_status.setText("<span style='color:#DC2626;'>○</span> <span style='color:#64748B;'>读卡器未就绪</span>")
            self.on_card_removed()

    def on_status_update(self, state: str, message: str):
        pass

    # -------------------------------------------------------------
    # 顶部菜单栏与全局快捷键 (Native Menu Bar & Hotkeys)
    # -------------------------------------------------------------
    def setup_menu_bar(self):
        menubar = self.menuBar()

        # 1. 文件 (File)
        menu_file = menubar.addMenu("文件(&F)")

        act_new_recipe = QAction("新建配方(&N)", self)
        act_new_recipe.setShortcut(QKeySequence.New)
        act_new_recipe.triggered.connect(self.new_recipe)
        menu_file.addAction(act_new_recipe)

        act_import_recipe = QAction("导入配方...(&O)", self)
        act_import_recipe.setShortcut(QKeySequence.Open)
        act_import_recipe.triggered.connect(self.import_recipe_file)
        menu_file.addAction(act_import_recipe)

        act_export_recipe = QAction("导出配方...(&S)", self)
        act_export_recipe.setShortcut(QKeySequence.Save)
        act_export_recipe.triggered.connect(self.export_recipe_file)
        menu_file.addAction(act_export_recipe)

        menu_file.addSeparator()

        act_export_csv = QAction("导出作业清单 CSV...(&E)", self)
        act_export_csv.setShortcut(QKeySequence("Ctrl+E"))
        act_export_csv.triggered.connect(self.export_records)
        menu_file.addAction(act_export_csv)

        menu_file.addSeparator()

        act_quit = QAction("退出程序(&Q)", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        menu_file.addAction(act_quit)

        # 2. 硬件与操作 (Hardware & Operation)
        menu_hw = menubar.addMenu("硬件与操作(&H)")

        act_refresh_reader = QAction("重新扫描物理读卡器(&R)", self)
        act_refresh_reader.setShortcut(QKeySequence.Refresh)
        act_refresh_reader.triggered.connect(self.on_refresh_reader_clicked)
        menu_hw.addAction(act_refresh_reader)

        menu_hw.addSeparator()

        act_switch_mode = QAction("切换发卡模式 (单张/批量)(&M)", self)
        act_switch_mode.setShortcut(QKeySequence("Ctrl+M"))
        act_switch_mode.triggered.connect(self._toggle_mode_shortcut)
        menu_hw.addAction(act_switch_mode)

        # 3. 工具 (Tools)
        menu_tools = menubar.addMenu("工具(&T)")

        act_edit_recipe = QAction("调整当前配方参数...(&P)", self)
        act_edit_recipe.setShortcut(QKeySequence("Ctrl+Shift+R"))
        act_edit_recipe.triggered.connect(self.open_recipe_edit_dialog)
        menu_tools.addAction(act_edit_recipe)

        menu_tools.addSeparator()

        act_clear_log = QAction("清空通信与诊断日志(&L)", self)
        act_clear_log.setShortcut(QKeySequence("Ctrl+K"))
        act_clear_log.triggered.connect(lambda: self.txt_log.clear())
        menu_tools.addAction(act_clear_log)

        act_clear_records = QAction("清空作业明细记录(&C)", self)
        act_clear_records.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        act_clear_records.triggered.connect(self.clear_records)
        menu_tools.addAction(act_clear_records)

        # 4. 帮助 (Help)
        menu_help = menubar.addMenu("帮助(&H)")

        act_check_update = QAction("检查新版本...(&U)", self)
        act_check_update.triggered.connect(lambda: self.check_for_updates(manual=True))
        menu_help.addAction(act_check_update)

        act_github = QAction("访问 GitHub 仓库源码", self)
        act_github.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{APP_GITHUB_REPO}")))
        menu_help.addAction(act_github)

        menu_help.addSeparator()

        act_about = QAction("关于 NTAG424 Pro(&A)...", self)
        act_about.triggered.connect(self.show_about_dialog)
        menu_help.addAction(act_about)

    def _toggle_mode_shortcut(self):
        is_single = self.radio_mode_single.isChecked()
        if is_single:
            self.radio_mode_batch.setChecked(True)
        else:
            self.radio_mode_single.setChecked(True)
        self.on_work_mode_switched()

    def new_recipe(self):
        if QMessageBox.question(self, "新建配方", "确定要基于系统默认模板创建全新配方吗？当前未导出的配置将被重置。", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.config = DEFAULT_CONFIG.copy()
            self.config["recipe_name"] = generate_random_recipe_name()
            save_config(self.config)
            self.sync_worker_config()
            self.update_recipe_banner()
            self.append_log(f"[CONFIG] 已新建默认配方: {self.config.get('recipe_name', '')}")
            self.open_recipe_edit_dialog()

    def import_recipe_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入配方文件 (JSON)",
            "",
            "JSON 配方文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("文件内容必须是 JSON 对象")

            if "config" in data and isinstance(data["config"], dict):
                data = {**data, **data["config"]}

            new_cfg = self.config.copy()
            for k in DEFAULT_CONFIG.keys():
                if k in data:
                    new_cfg[k] = data[k]

            if "system_salt" in data and "kdf_custom_salt" not in data:
                new_cfg["kdf_custom_salt"] = data["system_salt"]

            if "recipe_name" not in data:
                new_cfg["recipe_name"] = os.path.splitext(os.path.basename(file_path))[0]

            self.config = new_cfg
            save_config(self.config)
            self.sync_worker_config()
            self.update_recipe_banner()
            self.append_log(f"[CONFIG] 成功导入外部配方: {self.config.get('recipe_name', '')}")
            QMessageBox.information(self, "导入成功", f"配方已成功加载并生效！\n配方名: {self.config.get('recipe_name', '')}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法解析配方文件:\n{e}")

    def export_recipe_file(self):
        recipe_name = self.config.get("recipe_name", "recipe")
        default_filename = f"{recipe_name}_{datetime.now().strftime('%Y%m%d')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前配方 (JSON)",
            default_filename,
            "JSON 配方文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            recipe_data = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": APP_VERSION,
                **self.config
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(recipe_data, f, indent=2, ensure_ascii=False)

            self.append_log(f"[CONFIG] 配方已导出至: {file_path}")
            QMessageBox.information(self, "导出成功", f"配方已成功导出至:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"无法写入配方文件:\n{e}")

    # -------------------------------------------------------------
    # 快捷键事件分发 (Space 发卡 / Esc 暂停)
    # -------------------------------------------------------------
    def keyPressEvent(self, event):
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QSpinBox)):
            super().keyPressEvent(event)
            return

        key = event.key()
        # 空格键：单张模式下一键触发【发卡注入】
        if key == Qt.Key_Space:
            if self.radio_mode_single.isChecked() and self.btn_single_provision.isEnabled():
                self.on_single_action_clicked("provision")
                event.accept()
                return

        # Esc 键：批量流水线模式下一键暂停/恢复作业
        elif key == Qt.Key_Escape:
            if not self.radio_mode_single.isChecked():
                self.toggle_batch_running()
                event.accept()
                return

        super().keyPressEvent(event)

    # -------------------------------------------------------------
    # 在线检查更新与关于
    # -------------------------------------------------------------
    def check_for_updates(self, manual: bool = True):
        if self.update_checker_thread and self.update_checker_thread.isRunning():
            return
        self.update_checker_thread = UpdateCheckThread(self)
        self.update_checker_thread.check_finished.connect(
            lambda has_up, tag, url, body, err: self.on_update_check_finished(has_up, tag, url, body, err, manual)
        )
        self.update_checker_thread.start()
        if manual:
            self.statusBar().showMessage("正在检查更新...", 3000)

    def on_update_check_finished(self, has_update: bool, latest_tag: str, release_url: str, release_notes: str, error_msg: str, manual: bool):
        if error_msg:
            if manual:
                QMessageBox.warning(self, "检查更新失败", f"无法连接到 GitHub 检查最新版本:\n{error_msg}")
            return

        if has_update:
            dlg = UpdateDialog(latest_tag, release_notes, release_url, self)
            dlg.exec()
        else:
            if manual:
                QMessageBox.information(self, "已是最新版本", f"当前版本 {APP_VERSION} 已是最新版本！无需更新。")

    def show_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()

    # -------------------------------------------------------------
    # 虚拟表格过滤与检索回调
    # -------------------------------------------------------------
    def update_table_filter_badge(self):
        total = self.table_model.rowCount()
        shown = self.proxy_model.rowCount()
        is_filtered = bool(self.input_table_search.text().strip() or (self.combo_table_status.currentData() != "ALL"))

        if is_filtered:
            self.lbl_table_badge.setText(f"已筛选: {shown} / {total} 条")
            self.lbl_table_badge.setStyleSheet("""
                QLabel {
                    background-color: #EFF6FF;
                    color: #1D4ED8;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 9px;
                    border: 1px solid #BFDBFE;
                }
            """)
        else:
            self.lbl_table_badge.setText(f"共 {total} 条")
            self.lbl_table_badge.setStyleSheet("""
                QLabel {
                    background-color: #E2E8F0;
                    color: #475569;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 9px;
                    border: 1px solid #CBD5E1;
                }
            """)

    def on_table_search_changed(self, text: str):
        self.proxy_model.set_keyword(text)
        self.update_table_filter_badge()

    def on_table_status_filter_changed(self, idx: int):
        status = self.combo_table_status.currentData()
        self.proxy_model.set_status_filter(status or "ALL")
        self.update_table_filter_badge()

    # -------------------------------------------------------------
    # 作业记录与导出 (基于虚拟数据模型)
    # -------------------------------------------------------------
    def on_tag_processed(self, record: dict):
        self.table_model.add_record(record)
        self.table.scrollToBottom()

        total = len(self.table_model._records)
        succ = sum(1 for r in self.table_model._records if r.get("status") == "SUCCESS")
        fail = total - succ
        self.lbl_batch_stats.setText(f"已处理: {total} 张  |  成功: {succ}  |  失败: {fail}")
        self.update_table_filter_badge()

    def export_records(self):
        records = self.table_model.get_records()
        if not records:
            QMessageBox.information(self, "提示", "当前没有可导出的作业记录。")
            return
        default_filename = f"records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出作业记录", default_filename, "CSV 文件 (*.csv)")
        if path:
            if export_to_csv(records, path):
                self.append_log(f"[INFO] 记录已导出至: {path}")
                QMessageBox.information(self, "导出成功", f"作业清单已导出至:\n{path}")
            else:
                QMessageBox.warning(self, "导出失败", "写入 CSV 文件发生异常，请检查文件权限。")

    def clear_records(self):
        if QMessageBox.question(self, "清空确认", "确定清空当前作业明细记录吗？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.table_model.clear()
            self.lbl_batch_stats.setText("已处理: 0 张  |  成功: 0  |  失败: 0")
            self.append_log("[INFO] 已清空作业明细记录")
            self.update_table_filter_badge()

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()


def main():
    # Windows: Set explicit AppUserModelID to ensure taskbar icon displays correctly
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bestqiu.ntag424.provisioner.1.0")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("NTAG424 Pro")
    app.setApplicationDisplayName("NTAG424 Pro")

    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
