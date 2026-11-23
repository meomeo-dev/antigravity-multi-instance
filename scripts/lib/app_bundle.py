"""macOS .app launcher bundle generator with color-coded icons and Desktop shortcuts."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from lib import icon_builder, profiles

BUNDLE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]{0,47}$")
LSREGISTER_BIN = Path(
    "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
)


def validate_bundle_name(name: str) -> str:
    """Validate macOS .app display/stem name."""
    cleaned = name.strip()
    if not BUNDLE_NAME_RE.match(cleaned) or ".." in cleaned:
        raise ValueError(f"无效的 .app 名称 '{name}'：仅允许字母、数字、空格、连字符和下划线")
    return cleaned


def render_info_plist(bundle_name: str, bundle_id: str, executable: str = "launcher") -> str:
    """Render a minimal macOS Info.plist for a color-coded launcher .app bundle."""
    safe_name = escape(bundle_name)
    safe_id = escape(bundle_id)
    safe_exec = escape(executable)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        f"  <key>CFBundleDisplayName</key><string>{safe_name}</string>\n"
        f"  <key>CFBundleExecutable</key><string>{safe_exec}</string>\n"
        "  <key>CFBundleIconFile</key><string>AppIcon.icns</string>\n"
        f"  <key>CFBundleIdentifier</key><string>{safe_id}</string>\n"
        "  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>\n"
        f"  <key>CFBundleName</key><string>{safe_name}</string>\n"
        "  <key>CFBundlePackageType</key><string>APPL</string>\n"
        "  <key>CFBundleShortVersionString</key><string>1.0</string>\n"
        "  <key>CFBundleVersion</key><string>1</string>\n"
        "  <key>LSUIElement</key><true/>\n"
        "  <key>NSHighResolutionCapable</key><true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


def render_bundle_executable(launcher_path: Path) -> str:
    """Render Contents/MacOS/launcher delegating to the profile's canonical launcher script."""
    return f"#!/bin/bash\nset -euo pipefail\nexec {shlex.quote(str(launcher_path))} \"$@\"\n"


def _write_plist(plist_path: Path, content: str, dry_run: bool, actions: list[dict[str, object]]) -> None:
    existing = plist_path.read_text(encoding="utf-8") if plist_path.is_file() else None
    if existing == content:
        actions.append({"action": "write_plist", "path": str(plist_path), "status": "unchanged"})
        return
    if dry_run:
        status = "planned_update" if existing is not None else "planned_create"
        actions.append({"action": "write_plist", "path": str(plist_path), "status": status})
        return
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(content, encoding="utf-8")
    actions.append({"action": "write_plist", "path": str(plist_path), "status": "updated" if existing else "created"})


def _build_bundle_icon(
    app_bundle: Path,
    icns_path: Path,
    icon_color: str,
    source_app_path: Path,
    dry_run: bool,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> dict[str, object]:
    if dry_run:
        actions.append({"action": "build_icon", "path": str(icns_path), "color": icon_color, "status": "planned"})
        return {"built": False, "color": icon_color, "planned": True}
    icon_meta = icon_builder.build_colored_icns(icns_path, icon_color, source_app_path)
    status = "created" if icon_meta.get("built") else "skipped"
    actions.append({"action": "build_icon", "path": str(icns_path), "color": icon_color, "status": status})
    if not icon_meta.get("built"):
        warnings.append(f"图标编译跳过: {icon_meta.get('reason', 'unknown')}")
    os.utime(app_bundle, None)
    if LSREGISTER_BIN.is_file() and os.access(LSREGISTER_BIN, os.X_OK):
        subprocess.run([str(LSREGISTER_BIN), "-f", str(app_bundle)], capture_output=True, check=False)
    return icon_meta


def create_app_bundle(
    home: Path,
    kind: str,
    slug: str,
    bundle_name: str,
    launcher_path: Path,
    icon_color: str,
    source_app_path: Path,
    desktop_shortcut: bool,
    dry_run: bool,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> dict[str, object]:
    """Create ~/Applications/<bundle_name>.app with colored icon and optional Desktop symlink."""
    app_bundle = home / "Applications" / f"{bundle_name}.app"
    contents = app_bundle / "Contents"
    icns_path = contents / "Resources" / "AppIcon.icns"
    bundle_id = f"local.antigravity-multi.{kind}.{slug}"

    profiles.ensure_dir(contents / "MacOS", dry_run, actions)
    profiles.ensure_dir(contents / "Resources", dry_run, actions)
    _write_plist(contents / "Info.plist", render_info_plist(bundle_name, bundle_id), dry_run, actions)
    profiles.write_executable(contents / "MacOS" / "launcher", render_bundle_executable(launcher_path), dry_run, actions)
    icon_meta = _build_bundle_icon(app_bundle, icns_path, icon_color, source_app_path, dry_run, actions, warnings)

    shortcut_path = home / "Desktop" / f"{bundle_name}.app" if desktop_shortcut else None
    if shortcut_path is not None:
        res = profiles.ensure_symlink(shortcut_path, app_bundle, dry_run, actions)
        if res["status"] == "conflict":
            warnings.append(f"桌面已存在冲突项，已跳过快捷方式: {shortcut_path}")

    return {
        "bundle_path": str(app_bundle),
        "bundle_id": bundle_id,
        "icon_color": icon_color,
        "icon_path": str(icns_path),
        "icon_meta": icon_meta,
        "desktop_shortcut": str(shortcut_path) if shortcut_path else None,
    }
