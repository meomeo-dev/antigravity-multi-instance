"""Shared path, discovery, symlink, and shell-config helpers for Antigravity multi-instance tools."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Callable

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_NOT_READY = 3

PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ALIAS_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")
RESERVED_NAMES = frozenset({"default", "cli", "config", "bin", "lib", "shared"})

CLI_DEFAULT_DIR = "antigravity-cli"
CLI_PREFIX = "antigravity-cli-"
PROFILES_ZSH_REL = Path(".config/antigravity-multi/profiles.zsh")
DESKTOP_ROOT_REL = Path(".agy-profiles")
ZSHRC_BLOCK_ID = "source-profiles"

DESKTOP_APPS: dict[str, dict[str, str | None]] = {
    "app": {
        "label": "Google Antigravity (2.0)",
        "bundle_name": "Antigravity.app",
        "default_app_path": "/Applications/Antigravity.app",
        "brew_cask": "antigravity",
        "support_prefix": "Antigravity",
        "gemini_subdir": "antigravity",
        "alias_prefix": "agy-app-",
        "extensions_rel": None,
    },
    "ide": {
        "label": "Google Antigravity IDE",
        "bundle_name": "Antigravity IDE.app",
        "default_app_path": "/Applications/Antigravity IDE.app",
        "brew_cask": "antigravity-ide",
        "support_prefix": "Antigravity IDE",
        "gemini_subdir": "antigravity-ide",
        "alias_prefix": "agy-ide-",
        "extensions_rel": ".antigravity-ide/extensions",
    },
}


def resolve_home(home_arg: str | None) -> Path:
    """Resolve target home directory from explicit argument or HOME environment."""
    if home_arg:
        return Path(home_arg).expanduser().resolve()
    return Path.home().resolve()


def validate_profile_name(name: str) -> str:
    """Validate profile slug to prevent path traversal or reserved collisions."""
    cleaned = name.strip()
    if not PROFILE_NAME_RE.match(cleaned) or cleaned in RESERVED_NAMES:
        raise ValueError(
            f"无效的 profile 名称 '{name}'：须匹配 ^[a-z0-9][a-z0-9_-]{{0,31}}$ 且不能为保留名"
        )
    return cleaned


def validate_alias_name(alias_name: str) -> str:
    """Validate shell alias/function identifier."""
    cleaned = alias_name.strip()
    if not ALIAS_NAME_RE.match(cleaned):
        raise ValueError(f"无效的命令别名 '{alias_name}'：仅允许字母、数字、连字符和下划线")
    return cleaned


def cli_data_dir(home: Path, name: str) -> tuple[str, Path]:
    """Return (<app_data_dir_name>, <full_path>) for a CLI profile."""
    dir_name = f"{CLI_PREFIX}{name}"
    return dir_name, home / ".gemini" / dir_name


def desktop_paths(home: Path, kind: str, name: str) -> dict[str, Path | None]:
    """Compute isolated paths for a desktop profile."""
    spec = DESKTOP_APPS[kind]
    profile_home = home / DESKTOP_ROOT_REL / f"{kind}-{name}"
    support_prefix = str(spec["support_prefix"])
    user_data_dir = home / "Library" / "Application Support" / f"{support_prefix}-{name}"
    launcher_path = home / DESKTOP_ROOT_REL / "bin" / f"{spec['alias_prefix']}{name}"
    ext_rel = spec["extensions_rel"]
    shared_ext_dir = (home / ext_rel) if ext_rel else None
    return {
        "profile_home": profile_home,
        "gemini_dir": profile_home / ".gemini",
        "config_link": profile_home / ".gemini" / "config",
        "user_data_dir": user_data_dir,
        "launcher_path": launcher_path,
        "shared_extensions_dir": shared_ext_dir,
    }


def ensure_dir(path: Path, dry_run: bool, actions: list[dict]) -> None:
    """Create directory if absent and record action."""
    if path.is_dir():
        actions.append({"action": "mkdir", "path": str(path), "status": "exists"})
        return
    if dry_run:
        actions.append({"action": "mkdir", "path": str(path), "status": "planned"})
        return
    path.mkdir(parents=True, exist_ok=True)
    actions.append({"action": "mkdir", "path": str(path), "status": "created"})


def ensure_symlink(
    link_path: Path, target: Path, dry_run: bool, actions: list[dict]
) -> dict:
    """Create symlink safely without overwriting existing non-symlink paths."""
    if link_path.is_symlink():
        current = Path(os.readlink(link_path))
        if current == target or link_path.resolve() == target.resolve():
            item = {"action": "symlink", "path": str(link_path), "target": str(target), "status": "exists"}
            actions.append(item)
            return item
        item = {
            "action": "symlink",
            "path": str(link_path),
            "target": str(target),
            "existing_target": str(current),
            "status": "conflict",
        }
        actions.append(item)
        return item
    if link_path.exists():
        item = {"action": "symlink", "path": str(link_path), "target": str(target), "status": "conflict"}
        actions.append(item)
        return item
    if dry_run:
        item = {"action": "symlink", "path": str(link_path), "target": str(target), "status": "planned"}
        actions.append(item)
        return item
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target)
    item = {"action": "symlink", "path": str(link_path), "target": str(target), "status": "created"}
    actions.append(item)
    return item


def write_executable(path: Path, content: str, dry_run: bool, actions: list[dict]) -> None:
    """Write an executable script file idempotently."""
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    if existing == content and os.access(path, os.X_OK):
        actions.append({"action": "write_script", "path": str(path), "status": "unchanged"})
        return
    if dry_run:
        status = "planned_update" if existing is not None else "planned_create"
        actions.append({"action": "write_script", "path": str(path), "status": status})
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    status = "updated" if existing is not None else "created"
    actions.append({"action": "write_script", "path": str(path), "status": status})


def upsert_managed_block(
    file_path: Path, block_id: str, body_lines: list[str], dry_run: bool, actions: list[dict]
) -> None:
    """Insert or replace a named managed block inside a shell config file."""
    start_marker = f"# >>> agy-multi:{block_id} >>>"
    end_marker = f"# <<< agy-multi:{block_id} <<<"
    block_text = "\n".join([start_marker, *body_lines, end_marker])
    original = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
    pattern = re.compile(
        rf"^{re.escape(start_marker)}\n.*?^{re.escape(end_marker)}$",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(original):
        updated = pattern.sub(lambda _m: block_text, original)
    else:
        sep = "\n\n" if original.strip() else ""
        updated = f"{original.rstrip()}{sep}{block_text}\n"
    if updated == original:
        actions.append({"action": "managed_block", "path": str(file_path), "block": block_id, "status": "unchanged"})
        return
    if dry_run:
        actions.append({"action": "managed_block", "path": str(file_path), "block": block_id, "status": "planned"})
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(updated, encoding="utf-8")
    actions.append({"action": "managed_block", "path": str(file_path), "block": block_id, "status": "updated"})


def ensure_zshrc_source(
    home: Path, profiles_zsh: Path, dry_run: bool, actions: list[dict]
) -> None:
    """Ensure ~/.zshrc sources the standalone profiles.zsh file via a managed block."""
    zshrc = home / ".zshrc"
    quoted = shlex.quote(str(profiles_zsh))
    lines = [f'[[ -f {quoted} ]] && source {quoted}']
    upsert_managed_block(zshrc, ZSHRC_BLOCK_ID, lines, dry_run, actions)


def render_cli_shell_lines(
    alias_name: str, data_dir_name: str, set_tab_title: bool
) -> list[str]:
    """Render shell alias or tab-titling wrapper function for an isolated agy CLI profile."""
    if not set_tab_title:
        return [f"alias {alias_name}='SSH_CONNECTION=1 agy --app_data_dir={data_dir_name}'"]
    return [
        f"{alias_name}() {{",
        f"  printf '\\e]1;{alias_name}\\a'",
        f'  SSH_CONNECTION=1 agy --app_data_dir={shlex.quote(data_dir_name)} "$@"',
        "}",
    ]


def render_desktop_launcher(
    kind: str,
    app_path: str,
    profile_home: Path,
    user_data_dir: Path,
    extensions_dir: Path | None,
) -> str:
    """Render an executable macOS launcher script using open -n --env --args."""
    spec = DESKTOP_APPS[kind]
    cask = spec["brew_cask"]
    args_parts = [f'--user-data-dir="$USER_DATA_DIR"']
    ext_line = ""
    if extensions_dir is not None:
        ext_line = f'EXTENSIONS_DIR={shlex.quote(str(extensions_dir))}\n'
        args_parts.append('--extensions-dir="$EXTENSIONS_DIR"')
    args_str = " ".join(args_parts)
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n\n"
        f"APP_PATH={shlex.quote(app_path)}\n"
        f"PROFILE_HOME={shlex.quote(str(profile_home))}\n"
        f"USER_DATA_DIR={shlex.quote(str(user_data_dir))}\n"
        f"{ext_line}"
        'if [ ! -d "$APP_PATH" ]; then\n'
        '  echo "未找到桌面客户端: $APP_PATH" >&2\n'
        f'  echo "请先安装: brew install --cask {cask}" >&2\n'
        "  exit 3\n"
        "fi\n"
        'mkdir -p "$PROFILE_HOME/.gemini" "$USER_DATA_DIR"\n'
        'exec /usr/bin/open -n -a "$APP_PATH" \\\n'
        '  --env SSH_CONNECTION=1 \\\n'
        '  --env HOME="$PROFILE_HOME" \\\n'
        f'  --args {args_str} "$@"\n'
    )


def render_desktop_shell_lines(alias_name: str, launcher_path: Path) -> list[str]:
    """Render shell alias invoking a desktop profile launcher script."""
    return [f"alias {alias_name}={shlex.quote(str(launcher_path))}"]


def read_safe_settings(settings_path: Path) -> dict[str, object]:
    """Read only non-sensitive display metadata from settings.json."""
    if not settings_path.is_file():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"parse_error": True}
    if not isinstance(data, dict):
        return {}
    return {
        "model": data.get("model"),
        "colorScheme": data.get("colorScheme"),
    }


def inspect_symlink_info(path: Path) -> dict[str, object]:
    """Inspect whether a path is a valid symlink, broken symlink, directory, or missing."""
    if path.is_symlink():
        target = os.readlink(path)
        return {"type": "symlink", "target": target, "broken": not path.exists()}
    if path.is_dir():
        return {"type": "directory", "broken": False}
    if path.exists():
        return {"type": "file", "broken": False}
    return {"type": "missing", "broken": False}


def detect_installations(
    applications_dir: Path, which_fn: Callable[[str], str | None] = shutil.which
) -> dict[str, dict[str, object]]:
    """Detect installed Antigravity CLI binaries and macOS desktop app bundles."""
    app_bundle = applications_dir / "Antigravity.app"
    ide_bundle = applications_dir / "Antigravity IDE.app"
    agy_bin = which_fn("agy")
    agy_ide_bin = which_fn("agy-ide") or which_fn("antigravity-ide")
    return {
        "cli": {"installed": bool(agy_bin), "path": agy_bin},
        "desktop_app": {"installed": app_bundle.is_dir(), "path": str(app_bundle)},
        "desktop_ide": {
            "installed": ide_bundle.is_dir(),
            "path": str(ide_bundle),
            "cli_path": agy_ide_bin,
        },
    }


def inspect_cli_profiles(home: Path) -> list[dict[str, object]]:
    """Discover ~/.gemini/antigravity-cli* directories without reading any secrets."""
    gemini_root = home / ".gemini"
    if not gemini_root.is_dir():
        return []
    profiles: list[dict[str, object]] = []
    for entry in sorted(gemini_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name != CLI_DEFAULT_DIR and not entry.name.startswith(CLI_PREFIX):
            continue
        token_path = entry / "antigravity-oauth-token"
        token_exists = token_path.is_file()
        token_mode = oct(token_path.stat().st_mode & 0o777) if token_exists else None
        convs_dir = entry / "conversations"
        conv_count = sum(1 for _ in convs_dir.iterdir()) if convs_dir.is_dir() else 0
        profiles.append(
            {
                "dir_name": entry.name,
                "path": str(entry),
                "is_default": entry.name == CLI_DEFAULT_DIR,
                "auth_storage": "local_token_file" if token_exists else "keychain_or_unauthenticated",
                "token_file_present": token_exists,
                "token_file_mode": token_mode,
                "skills": inspect_symlink_info(entry / "skills"),
                "settings": read_safe_settings(entry / "settings.json"),
                "conversation_entries": conv_count,
            }
        )
    return profiles


def inspect_desktop_profiles(home: Path) -> list[dict[str, object]]:
    """Discover isolated desktop profiles under ~/.agy-profiles/."""
    root = home / DESKTOP_ROOT_REL
    if not root.is_dir():
        return []
    found: list[dict[str, object]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name == "bin":
            continue
        kind = "ide" if entry.name.startswith("ide-") else "app" if entry.name.startswith("app-") else "custom"
        slug = entry.name.split("-", 1)[1] if "-" in entry.name else entry.name
        spec = DESKTOP_APPS.get(kind, DESKTOP_APPS["app"])
        gemini_sub = entry / ".gemini" / str(spec["gemini_subdir"])
        user_data_dir = home / "Library" / "Application Support" / f"{spec['support_prefix']}-{slug}"
        launcher = root / "bin" / f"{spec['alias_prefix']}{slug}"
        found.append(
            {
                "profile_dir": entry.name,
                "kind": kind,
                "name": slug,
                "profile_home": str(entry),
                "user_data_dir": str(user_data_dir),
                "user_data_initialized": user_data_dir.is_dir() and any(user_data_dir.iterdir()),
                "config_symlink": inspect_symlink_info(entry / ".gemini" / "config"),
                "backend_dir_present": gemini_sub.is_dir(),
                "state_file_present": (gemini_sub / "antigravity_state.pbtxt").is_file(),
                "token_file_present": (gemini_sub / "antigravity-oauth-token").is_file(),
                "launcher_path": str(launcher),
                "launcher_ready": launcher.is_file() and os.access(launcher, os.X_OK),
            }
        )
    return found


def find_managed_app_bundles(home: Path) -> list[dict[str, object]]:
    """Discover managed launcher .app bundles under ~/Applications and their Desktop shortcuts."""
    apps_dir = home / "Applications"
    if not apps_dir.is_dir():
        return []
    bundles: list[dict[str, object]] = []
    for entry in sorted(apps_dir.glob("*.app")):
        plist = entry / "Contents" / "Info.plist"
        if not plist.is_file():
            continue
        text = plist.read_text(encoding="utf-8", errors="ignore")
        if "local.antigravity-multi." not in text:
            continue
        desktop_link = home / "Desktop" / entry.name
        bundles.append(
            {
                "name": entry.stem,
                "bundle_path": str(entry),
                "has_icon": (entry / "Contents" / "Resources" / "AppIcon.icns").is_file(),
                "desktop_shortcut": inspect_symlink_info(desktop_link),
            }
        )
    return bundles


def scan_shell_definitions(home: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Scan ~/.zshrc and managed profiles.zsh for Antigravity aliases and anti-patterns."""
    files = [home / ".zshrc", home / PROFILES_ZSH_REL]
    entries: list[dict[str, str]] = []
    warnings: list[str] = []
    seen_aliases: dict[str, str] = {}
    alias_re = re.compile(r"^\s*alias\s+([a-zA-Z0-9_-]+)=(.+)$")
    for path in files:
        if not path.is_file():
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not any(k in stripped for k in ("agy", "Antigravity", "antigravity")):
                continue
            match = alias_re.match(stripped)
            if not match:
                continue
            name, value = match.group(1), match.group(2)
            entries.append({"name": name, "source": f"{path}:{lineno}", "definition": value})
            if name in seen_aliases:
                warnings.append(f"重复别名 '{name}' 同时定义在 {seen_aliases[name]} 与 {path}:{lineno}")
            seen_aliases[name] = f"{path}:{lineno}"
            if "SSH_CONNECTION=1" in value and "open " in value and "--env" not in value:
                warnings.append(
                    f"{path}:{lineno} 中 '{name}' 将 SSH_CONNECTION=1 写在 open 之前，macOS LaunchServices 不会继承该变量，请改用 open --env SSH_CONNECTION=1"
                )
            if "--user-data-dir" in value and "open " in value and "--env HOME=" not in value:
                warnings.append(
                    f"{path}:{lineno} 中 '{name}' 只指定了 --user-data-dir 而未隔离 HOME，同款桌面端多账号仍可能共用 ~/.gemini/antigravity*"
                )
    return entries, warnings
