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
    QImage, QPainter, QColor, QPen, QLinearGradient, QRadialGradient, QPainterPath
)
from PySide6.QtCore import Qt, QRectF, QPointF

def draw_icon(size: int = 512) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    scale = size / 512.0
    
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    
    # 1. macOS Tile Base (420x420 centered in 512x512, Apple HIG standard squircle)
    tile_w, tile_h = 420 * scale, 420 * scale
    tile_x, tile_y = (size - tile_w) / 2, (size - tile_h) / 2 - 2 * scale
    radius = 94 * scale
    
    # Deep soft shadow
    shadow_path = QPainterPath()
    shadow_path.addRoundedRect(QRectF(tile_x, tile_y + 14 * scale, tile_w, tile_h), radius, radius)
    p.fillPath(shadow_path, QColor(0, 0, 0, 80))
    
    # Base squircle: Deep Titanium Midnight to Electric Cobalt
    bg_grad = QLinearGradient(tile_x, tile_y, tile_x + tile_w, tile_y + tile_h)
    bg_grad.setColorAt(0.0, QColor("#1E293B"))  # Slate 800
    bg_grad.setColorAt(0.4, QColor("#0F172A"))  # Slate 900
    bg_grad.setColorAt(1.0, QColor("#0B132B"))  # Deep Navy Midnight
    
    tile_path = QPainterPath()
    tile_path.addRoundedRect(QRectF(tile_x, tile_y, tile_w, tile_h), radius, radius)
    
    # Subtle outer bevel
    p.setPen(QPen(QColor(255, 255, 255, 35), 1.5 * scale))
    p.setBrush(bg_grad)
    p.drawPath(tile_path)
    
    # Center ambient glow
    ambient = QRadialGradient(size / 2, size / 2, 200 * scale)
    ambient.setColorAt(0.0, QColor(37, 99, 235, 60))
    ambient.setColorAt(0.8, QColor(30, 58, 138, 15))
    ambient.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(ambient)
    p.drawPath(tile_path)
    
    # 2. Hero Object: Floating Smartcard in Vibrant Blue
    card_w, card_h = 300 * scale, 190 * scale
    card_x = (size - card_w) / 2
    card_y = (size - card_h) / 2 + 12 * scale
    card_rect = QRectF(card_x, card_y, card_w, card_h)
    card_radius = 18 * scale
    
    # Card drop shadow
    c_shadow = QPainterPath()
    c_shadow.addRoundedRect(QRectF(card_x, card_y + 10 * scale, card_w, card_h), card_radius, card_radius)
    p.fillPath(c_shadow, QColor(0, 0, 0, 100))
    
    # Card body: Royal Blue gradient
    card_grad = QLinearGradient(card_x, card_y, card_x + card_w, card_y + card_h)
    card_grad.setColorAt(0.0, QColor("#2563EB"))  # Blue 600
    card_grad.setColorAt(0.55, QColor("#1D4ED8")) # Blue 700
    card_grad.setColorAt(1.0, QColor("#1E1B4B"))  # Indigo 950
    
    card_path = QPainterPath()
    card_path.addRoundedRect(card_rect, card_radius, card_radius)
    p.setPen(QPen(QColor("#60A5FA"), 2.2 * scale))
    p.setBrush(card_grad)
    p.drawPath(card_path)
    
    # Card gloss reflection (top half subtle highlight)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 18))
    p.drawRoundedRect(QRectF(card_x, card_y, card_w, card_h * 0.45), card_radius, card_radius)
    
    # 3. Gold Cryptographic Chip (Left side)
    chip_x = card_x + 32 * scale
    chip_y = card_y + 44 * scale
    chip_w = 56 * scale
    chip_h = 44 * scale
    chip_rect = QRectF(chip_x, chip_y, chip_w, chip_h)
    chip_radius = 8 * scale
    
    chip_grad = QLinearGradient(chip_x, chip_y, chip_x + chip_w, chip_y + chip_h)
    chip_grad.setColorAt(0.0, QColor("#FEF08A"))  # Yellow 200
    chip_grad.setColorAt(0.3, QColor("#FACC15"))  # Yellow 400
    chip_grad.setColorAt(0.7, QColor("#EAB308"))  # Yellow 500
    chip_grad.setColorAt(1.0, QColor("#A16207"))  # Yellow 700
    
    chip_path = QPainterPath()
    chip_path.addRoundedRect(chip_rect, chip_radius, chip_radius)
    p.setPen(QPen(QColor("#78350F"), 1.6 * scale))
    p.setBrush(chip_grad)
    p.drawPath(chip_path)
    
    # Chip circuit etching
    p.setPen(QPen(QColor("#78350F"), 1.4 * scale))
    p.drawLine(chip_x, chip_y + chip_h / 2, chip_x + chip_w, chip_y + chip_h / 2)
    p.drawLine(chip_x + chip_w * 0.35, chip_y, chip_x + chip_w * 0.35, chip_y + chip_h)
    p.drawLine(chip_x + chip_w * 0.65, chip_y, chip_x + chip_w * 0.65, chip_y + chip_h)
    
    # 4. Bold NFC Wireless Broadcast Waves (Right side)
    wave_cx = card_x + card_w - 75 * scale
    wave_cy = card_y + card_h / 2
    
    # Concentric signal waves opening towards right
    waves = [
        (22 * scale, "#FFFFFF", 4.2 * scale),
        (42 * scale, "#38BDF8", 3.8 * scale),
        (62 * scale, "#0284C7", 3.4 * scale),
    ]
    for r, col_hex, w in waves:
        pen = QPen(QColor(col_hex), w, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        arc_box = QRectF(wave_cx - r, wave_cy - r, 2 * r, 2 * r)
        p.drawArc(arc_box, -50 * 16, 100 * 16)
        
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QPointF(wave_cx, wave_cy), 4.5 * scale, 4.5 * scale)
    
    # 5. Security / DNA Shield in Card Bottom-Left (Sun verification badge)
    shield_cx = chip_x + chip_w / 2
    shield_cy = card_y + card_h - 35 * scale
    shield_w = 28 * scale
    shield_h = 32 * scale
    
    shield_path = QPainterPath()
    shield_path.moveTo(shield_cx, shield_cy - shield_h / 2)
    shield_path.lineTo(shield_cx + shield_w / 2, shield_cy - shield_h / 2 + 5 * scale)
    shield_path.quadTo(shield_cx + shield_w / 2, shield_cy + 8 * scale, shield_cx, shield_cy + shield_h / 2)
    shield_path.quadTo(shield_cx - shield_w / 2, shield_cy + 8 * scale, shield_cx - shield_w / 2, shield_cy - shield_h / 2 + 5 * scale)
    shield_path.closeSubpath()
    
    shield_grad = QLinearGradient(shield_cx, shield_cy - shield_h / 2, shield_cx, shield_cy + shield_h / 2)
    shield_grad.setColorAt(0.0, QColor("#10B981"))
    shield_grad.setColorAt(1.0, QColor("#047857"))
    p.setPen(QPen(QColor("#A7F3D0"), 1.4 * scale))
    p.setBrush(shield_grad)
    p.drawPath(shield_path)
    
    # Mini checkmark in shield
    p.setPen(QPen(QColor("#FFFFFF"), 2.2 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(shield_cx - 6 * scale, shield_cy, shield_cx - 2 * scale, shield_cy + 4 * scale)
    p.drawLine(shield_cx - 2 * scale, shield_cy + 4 * scale, shield_cx + 6 * scale, shield_cy - 4 * scale)
    
    p.end()
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
