"""
Generates high-resolution application icons for NTAG 424 DNA Provisioner.
Outputs:
- assets/icon.png (512x512)
- assets/icon.ico (Windows multi-res ICO)
- assets/icon.icns (macOS native ICNS via iconutil)
"""

import os
import struct
import subprocess
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QFont
)
from PySide6.QtCore import Qt, QRectF, QPointF

def draw_icon(size: int = 512) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    
    scale = size / 512.0
    
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    
    # 1. Background Squircle with Dark Indigo Gradient
    margin = 24 * scale
    radius = 96 * scale
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    
    bg_grad = QLinearGradient(0, 0, size, size)
    bg_grad.setColorAt(0.0, QColor("#1E293B"))  # Slate 800
    bg_grad.setColorAt(0.5, QColor("#0F172A"))  # Slate 900
    bg_grad.setColorAt(1.0, QColor("#020617"))  # Slate 950
    
    bg_path = QPainterPath()
    bg_path.addRoundedRect(rect, radius, radius)
    
    # Outer subtle glow border
    painter.setPen(QPen(QColor("#334155"), 2.5 * scale))
    painter.setBrush(bg_grad)
    painter.drawPath(bg_path)
    
    # 2. Stylized NFC Smart Card in the center
    # Card angled/tilted or flat modern perspective
    card_w = 260 * scale
    card_h = 160 * scale
    card_x = (size - card_w) / 2 - 15 * scale
    card_y = (size - card_h) / 2 + 35 * scale
    card_rect = QRectF(card_x, card_y, card_w, card_h)
    
    # Card drop shadow
    shadow_path = QPainterPath()
    shadow_path.addRoundedRect(QRectF(card_x, card_y + 8 * scale, card_w, card_h), 16 * scale, 16 * scale)
    painter.fillPath(shadow_path, QColor(0, 0, 0, 100))
    
    # Card Body: Royal Blue Gradient
    card_grad = QLinearGradient(card_x, card_y, card_x + card_w, card_y + card_h)
    card_grad.setColorAt(0.0, QColor("#2563EB"))  # Blue 600
    card_grad.setColorAt(0.7, QColor("#1D4ED8"))  # Blue 700
    card_grad.setColorAt(1.0, QColor("#0F172A"))  # Dark Blue / Slate
    
    card_path = QPainterPath()
    card_path.addRoundedRect(card_rect, 16 * scale, 16 * scale)
    painter.setPen(QPen(QColor("#60A5FA"), 2 * scale))
    painter.setBrush(card_grad)
    painter.drawPath(card_path)
    
    # Gold / Amber IC Chip on Card
    chip_x = card_x + 30 * scale
    chip_y = card_y + 35 * scale
    chip_w = 46 * scale
    chip_h = 36 * scale
    chip_rect = QRectF(chip_x, chip_y, chip_w, chip_h)
    
    chip_grad = QLinearGradient(chip_x, chip_y, chip_x + chip_w, chip_y + chip_h)
    chip_grad.setColorAt(0.0, QColor("#FDE047"))  # Gold 300
    chip_grad.setColorAt(0.5, QColor("#EAB308"))  # Gold 500
    chip_grad.setColorAt(1.0, QColor("#CA8A04"))  # Gold 600
    
    chip_path = QPainterPath()
    chip_path.addRoundedRect(chip_rect, 6 * scale, 6 * scale)
    painter.setPen(QPen(QColor("#A16207"), 1.5 * scale))
    painter.setBrush(chip_grad)
    painter.drawPath(chip_path)
    
    # Chip internal grid contacts
    painter.setPen(QPen(QColor("#A16207"), 1.2 * scale))
    painter.drawLine(chip_x, chip_y + chip_h / 2, chip_x + chip_w, chip_y + chip_h / 2)
    painter.drawLine(chip_x + chip_w / 3, chip_y, chip_x + chip_w / 3, chip_y + chip_h)
    painter.drawLine(chip_x + 2 * chip_w / 3, chip_y, chip_x + 2 * chip_w / 3, chip_y + chip_h)
    
    # Card Typography: "424 DNA"
    painter.setPen(QColor("#93C5FD"))
    font = QFont("Arial", int(14 * scale), QFont.Bold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 2 * scale)
    painter.setFont(font)
    painter.drawText(QRectF(card_x + 30 * scale, card_y + card_h - 40 * scale, 200 * scale, 25 * scale), Qt.AlignLeft | Qt.AlignVCenter, "NTAG 424 DNA")
    
    # 3. NFC Wireless Broadcast Waves (Cyan / Electric Sky Blue)
    # Originating from the top-right of the card upwards
    wave_center = QPointF(card_x + card_w - 20 * scale, card_y + 20 * scale)
    
    wave_colors = [
        QColor("#38BDF8"),  # Inner (brightest cyan)
        QColor("#0EA5E9"),  # Middle
        QColor("#0284C7"),  # Outer
    ]
    radii = [40 * scale, 70 * scale, 100 * scale]
    widths = [5.5 * scale, 4.5 * scale, 3.5 * scale]
    
    for r, col, w in zip(radii, wave_colors, widths):
        pen = QPen(col, w, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        # Arc from ~30 deg to ~120 deg
        arc_rect = QRectF(wave_center.x() - r, wave_center.y() - r, 2 * r, 2 * r)
        painter.drawArc(arc_rect, int(35 * 16), int(65 * 16))
    
    # 4. Security Verification Emblem / Shield (Emerald Green Badge)
    # Symbolizing SUN (Secure Unique NFC) / CMAC authentication
    shield_w = 64 * scale
    shield_h = 74 * scale
    shield_cx = card_x + card_w - 55 * scale
    shield_cy = card_y + card_h - 45 * scale
    
    shield_path = QPainterPath()
    shield_path.moveTo(shield_cx, shield_cy - shield_h / 2)
    shield_path.lineTo(shield_cx + shield_w / 2, shield_cy - shield_h / 2 + 10 * scale)
    shield_path.quadTo(shield_cx + shield_w / 2, shield_cy + 15 * scale, shield_cx, shield_cy + shield_h / 2)
    shield_path.quadTo(shield_cx - shield_w / 2, shield_cy + 15 * scale, shield_cx - shield_w / 2, shield_cy - shield_h / 2 + 10 * scale)
    shield_path.closeSubpath()
    
    shield_grad = QLinearGradient(shield_cx, shield_cy - shield_h / 2, shield_cx, shield_cy + shield_h / 2)
    shield_grad.setColorAt(0.0, QColor("#10B981"))  # Emerald 500
    shield_grad.setColorAt(1.0, QColor("#047857"))  # Emerald 700
    
    # Shield glow / border
    painter.setPen(QPen(QColor("#A7F3D0"), 2 * scale))
    painter.setBrush(shield_grad)
    painter.drawPath(shield_path)
    
    # White checkmark in shield
    check_pen = QPen(QColor("#FFFFFF"), 4 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(check_pen)
    painter.drawLine(shield_cx - 14 * scale, shield_cy + 2 * scale, shield_cx - 4 * scale, shield_cy + 12 * scale)
    painter.drawLine(shield_cx - 4 * scale, shield_cy + 12 * scale, shield_cx + 14 * scale, shield_cy - 10 * scale)
    
    painter.end()
    return img

def build_ico(images: dict, output_path: str):
    """Packages a dictionary of {size: png_bytes} into a valid multi-res ICO file."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + len(images) * 16
    
    dir_entries = b""
    image_data = b""
    
    for size, png_data in images.items():
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        length = len(png_data)
        
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, length, offset)
        dir_entries += entry
        image_data += png_data
        offset += length
        
    with open(output_path, "wb") as f:
        f.write(header + dir_entries + image_data)

def main():
    from PySide6.QtGui import QGuiApplication
    import sys
    app = QGuiApplication(sys.argv)
    assets_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Generate master PNG (512x512)
    master_img = draw_icon(512)
    png_path = os.path.join(assets_dir, "icon.png")
    master_img.save(png_path, "PNG")
    print(f"Saved: {png_path}")
    
    # 2. Generate multi-resolution ICO for Windows (16, 32, 48, 64, 128, 256)
    ico_sizes = [16, 32, 48, 64, 128, 256]
    ico_dict = {}
    for s in ico_sizes:
        sub_img = draw_icon(s)
        sub_path = os.path.join(assets_dir, f"icon_{s}.png")
        sub_img.save(sub_path, "PNG")
        with open(sub_path, "rb") as f:
            ico_dict[s] = f.read()
        os.remove(sub_path)
        
    ico_path = os.path.join(assets_dir, "icon.ico")
    build_ico(ico_dict, ico_path)
    print(f"Saved: {ico_path}")
    
    # 3. Generate native macOS ICNS via iconutil
    iconset_dir = os.path.join(assets_dir, "icon.iconset")
    os.makedirs(iconset_dir, exist_ok=True)
    
    mac_sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for s, name in mac_sizes:
        img = draw_icon(s)
        img.save(os.path.join(iconset_dir, name), "PNG")
        
    icns_path = os.path.join(assets_dir, "icon.icns")
    try:
        subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_path], check=True)
        print(f"Saved: {icns_path}")
    finally:
        import shutil
        shutil.rmtree(iconset_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
