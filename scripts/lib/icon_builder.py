"""Pure-stdlib macOS .app icon builder with color-coded squircle cards and badges."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

COLOR_PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "blue": {
        "bg_top": (59, 130, 246),
        "bg_bottom": (29, 78, 216),
        "border": (147, 197, 253),
        "badge": (37, 99, 235),
    },
    "purple": {
        "bg_top": (147, 51, 234),
        "bg_bottom": (88, 28, 135),
        "border": (216, 180, 254),
        "badge": (245, 158, 11),
    },
    "green": {
        "bg_top": (16, 185, 129),
        "bg_bottom": (4, 120, 87),
        "border": (167, 243, 208),
        "badge": (5, 150, 105),
    },
    "orange": {
        "bg_top": (249, 115, 22),
        "bg_bottom": (194, 65, 12),
        "border": (254, 215, 170),
        "badge": (234, 88, 12),
    },
    "red": {
        "bg_top": (239, 68, 68),
        "bg_bottom": (185, 28, 28),
        "border": (254, 202, 202),
        "badge": (220, 38, 38),
    },
    "teal": {
        "bg_top": (20, 184, 166),
        "bg_bottom": (15, 118, 110),
        "border": (153, 246, 228),
        "badge": (13, 148, 136),
    },
    "gold": {
        "bg_top": (245, 158, 11),
        "bg_bottom": (180, 83, 9),
        "border": (253, 230, 138),
        "badge": (217, 119, 6),
    },
    "slate": {
        "bg_top": (71, 85, 105),
        "bg_bottom": (30, 41, 59),
        "border": (203, 213, 225),
        "badge": (56, 189, 248),
    },
}

ICONSET_SPECS: tuple[tuple[str, int], ...] = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)


def encode_rgba_png(width: int, height: int, rgba: bytearray) -> bytes:
    """Encode 8-bit RGBA bytearray into a standard PNG byte stream."""
    stride = width * 4
    raw = bytearray((stride + 1) * height)
    for y in range(height):
        dst = y * (stride + 1)
        src = y * stride
        raw[dst] = 0
        raw[dst + 1 : dst + 1 + stride] = rgba[src : src + stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(bytes(raw), level=6)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", compressed) + _png_chunk(b"IEND", b"")


def _unfilter_row(ftype: int, row: bytearray, prev: bytearray, bpp: int) -> None:
    stride = len(row)
    if ftype == 1:
        for i in range(bpp, stride):
            row[i] = (row[i] + row[i - bpp]) & 255
    elif ftype == 2:
        for i in range(stride):
            row[i] = (row[i] + prev[i]) & 255
    elif ftype == 3:
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + ((a + prev[i]) >> 1)) & 255
    elif ftype == 4:
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            row[i] = (row[i] + pr) & 255


def decode_rgba_png(png_bytes: bytes) -> tuple[int, int, bytearray] | None:
    """Decode an 8-bit non-interlaced RGBA PNG into (w, h, bytearray)."""
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, width, height, idat = 8, 0, 0, bytearray()
    while pos + 8 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
        tag = png_bytes[pos + 4 : pos + 8]
        chunk = png_bytes[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, bit, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", chunk)
            if bit != 8 or ctype != 6 or interlace != 0:
                return None
        elif tag == b"IDAT":
            idat.extend(chunk)
        pos += 12 + length
    if width <= 0 or height <= 0:
        return None
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out, prev, cursor = bytearray(height * stride), bytearray(stride), 0
    for y in range(height):
        ftype = raw[cursor]
        row = bytearray(raw[cursor + 1 : cursor + 1 + stride])
        cursor += 1 + stride
        _unfilter_row(ftype, row, prev, 4)
        out[y * stride : (y + 1) * stride] = row
        prev = row
    return width, height, out


def _blend_pixel(buf: bytearray, idx: int, r: int, g: int, b: int, a: float) -> None:
    if a <= 0.0:
        return
    if a >= 1.0:
        buf[idx], buf[idx + 1], buf[idx + 2], buf[idx + 3] = r, g, b, 255
        return
    da = buf[idx + 3] / 255.0
    out_a = a + da * (1.0 - a)
    if out_a <= 0.0:
        return
    inv = da * (1.0 - a)
    buf[idx] = int((r * a + buf[idx] * inv) / out_a)
    buf[idx + 1] = int((g * a + buf[idx + 1] * inv) / out_a)
    buf[idx + 2] = int((b * a + buf[idx + 2] * inv) / out_a)
    buf[idx + 3] = int(out_a * 255)


def _signed_dist_round_rect(px: float, py: float, half: float, radius: float) -> float:
    qx = abs(px) - (half - radius)
    qy = abs(py) - (half - radius)
    out_d = math.hypot(max(qx, 0.0), max(qy, 0.0))
    in_d = min(max(qx, qy), 0.0)
    return out_d + in_d - radius


def render_card_background(size: int, palette: dict[str, tuple[int, int, int]]) -> bytearray:
    """Render a macOS squircle icon card with vertical gradient and colored border ring."""
    buf = bytearray(size * size * 4)
    center = (size - 1) / 2.0
    half = size * 0.41
    radius = half * 0.44
    border_w = size * 0.016
    t_r, t_g, t_b = palette["bg_top"]
    b_r, b_g, b_b = palette["bg_bottom"]
    br_r, br_g, br_b = palette["border"]
    for y in range(size):
        dy = y - center
        t = max(0.0, min(1.0, (dy + half) / (2.0 * half)))
        gr = int(t_r + (b_r - t_r) * t)
        gg = int(t_g + (b_g - t_g) * t)
        gb = int(t_b + (b_b - t_b) * t)
        row_off = y * size * 4
        for x in range(size):
            dist = _signed_dist_round_rect(x - center, dy, half, radius)
            if dist > 1.0:
                continue
            cov = max(0.0, min(1.0, 0.5 - dist))
            idx = row_off + x * 4
            if dist > -border_w:
                blend = max(0.0, min(1.0, (dist + border_w) / 1.5))
                cr = int(gr + (br_r - gr) * blend)
                cg = int(gg + (br_g - gg) * blend)
                cb = int(gb + (br_b - gb) * blend)
                _blend_pixel(buf, idx, cr, cg, cb, cov)
            else:
                _blend_pixel(buf, idx, gr, gg, gb, cov)
    return buf


def overlay_centered_rgba(
    canvas: bytearray, size: int, src_w: int, src_h: int, src: bytearray, scale: float = 0.80
) -> None:
    """Alpha-composite a source RGBA image scaled and centered onto the square canvas."""
    target = int(size * scale)
    offset = (size - target) // 2
    for y in range(target):
        sy = min(src_h - 1, int(y * src_h / target))
        dst_row = (offset + y) * size * 4
        src_row = sy * src_w * 4
        for x in range(target):
            sx = min(src_w - 1, int(x * src_w / target))
            s_idx = src_row + sx * 4
            sa = src[s_idx + 3] / 255.0
            if sa > 0.0:
                _blend_pixel(canvas, dst_row + (offset + x) * 4, src[s_idx], src[s_idx + 1], src[s_idx + 2], sa)


def draw_fallback_emblem(canvas: bytearray, size: int, color: tuple[int, int, int]) -> None:
    """Draw a minimal geometric arch when the official app icon is not installed."""
    cx, cy = size * 0.5, size * 0.52
    outer, inner = size * 0.22, size * 0.13
    r, g, b = color
    for y in range(int(size * 0.25), int(size * 0.76)):
        for x in range(int(size * 0.25), int(size * 0.76)):
            d = math.hypot(x - cx, (y - cy) * 0.85)
            if inner <= d <= outer and y <= cy + size * 0.18:
                _blend_pixel(canvas, (y * size + x) * 4, r, g, b, 0.95)


def draw_corner_badge(canvas: bytearray, size: int, badge_rgb: tuple[int, int, int]) -> None:
    """Draw a crisp bottom-right circular color badge with a white rim."""
    cx, cy = size * 0.77, size * 0.77
    r_outer, r_inner = size * 0.135, size * 0.105
    br, bg, bb = badge_rgb
    y0, y1 = max(0, int(cy - r_outer - 2)), min(size, int(cy + r_outer + 3))
    x0, x1 = max(0, int(cx - r_outer - 2)), min(size, int(cx + r_outer + 3))
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot(x - cx, y - cy)
            if d > r_outer + 1.0:
                continue
            idx = (y * size + x) * 4
            if d <= r_inner:
                _blend_pixel(canvas, idx, br, bg, bb, 1.0)
            elif d <= r_inner + 1.0:
                t = d - r_inner
                _blend_pixel(canvas, idx, int(br + (255 - br) * t), int(bg + (255 - bg) * t), int(bb + (255 - bb) * t), 1.0)
            else:
                _blend_pixel(canvas, idx, 255, 255, 255, max(0.0, min(1.0, r_outer + 0.5 - d)))


def find_source_icns(app_path: Path) -> Path | None:
    """Locate the primary .icns file inside a macOS .app bundle."""
    res_dir = app_path / "Contents" / "Resources"
    if not res_dir.is_dir():
        return None
    for name in ("icon.icns", "AppIcon.icns", "Code.icns"):
        cand = res_dir / name
        if cand.is_file():
            return cand
    found = sorted(res_dir.glob("*.icns"))
    return found[0] if found else None


def extract_base_rgba(icns_path: Path, tmp_dir: Path) -> tuple[int, int, bytearray] | None:
    """Extract the largest PNG from a source .icns via macOS iconutil."""
    if not shutil.which("iconutil"):
        return None
    iconset = tmp_dir / "src.iconset"
    proc = subprocess.run(
        ["iconutil", "-c", "iconset", "-o", str(iconset), str(icns_path)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not iconset.is_dir():
        return None
    for cand_name in ("icon_512x512.png", "icon_256x256@2x.png", "icon_256x256.png", "icon_128x128@2x.png"):
        cand = iconset / cand_name
        if cand.is_file():
            return decode_rgba_png(cand.read_bytes())
    return None


def _compile_icns_from_png(master_png: Path, size: int, tmp_dir: Path, output_icns: Path) -> None:
    out_iconset = tmp_dir / "out.iconset"
    out_iconset.mkdir()
    for filename, px in ICONSET_SPECS:
        dst = out_iconset / filename
        if px == size:
            shutil.copy2(master_png, dst)
        else:
            subprocess.run(["sips", "-z", str(px), str(px), str(master_png), "--out", str(dst)], capture_output=True, check=True)
    output_icns.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["iconutil", "-c", "icns", "-o", str(output_icns), str(out_iconset)], check=True)


def build_colored_icns(
    output_icns: Path, color_name: str, source_app_path: Path | None = None
) -> dict[str, object]:
    """Generate a color-coded macOS .icns icon file and return build metadata."""
    if color_name not in COLOR_PALETTES:
        raise ValueError(f"不支持的图标颜色 '{color_name}'，可选: {', '.join(sorted(COLOR_PALETTES))}")
    if not shutil.which("iconutil") or not shutil.which("sips"):
        return {"built": False, "reason": "iconutil 或 sips 不可用（仅 macOS 支持 .icns 编译）"}

    palette = COLOR_PALETTES[color_name]
    size = 512
    canvas = render_card_background(size, palette)
    used_source = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        icns_src = find_source_icns(source_app_path) if source_app_path else None
        base = extract_base_rgba(icns_src, tmp_dir) if icns_src else None
        if base is not None:
            overlay_centered_rgba(canvas, size, base[0], base[1], base[2])
            used_source = str(icns_src)
        else:
            draw_fallback_emblem(canvas, size, palette["border"])
        draw_corner_badge(canvas, size, palette["badge"])
        master_png = tmp_dir / "master_512.png"
        master_png.write_bytes(encode_rgba_png(size, size, canvas))
        _compile_icns_from_png(master_png, size, tmp_dir, output_icns)
    return {"built": True, "path": str(output_icns), "color": color_name, "base_icon": used_source}
