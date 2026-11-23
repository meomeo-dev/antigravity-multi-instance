#!/usr/bin/env python3
"""创建或维护 Antigravity 2.0 / IDE 同款桌面 App 多开隔离环境与启动入口

Skill: antigravity-multi-instance。遵守工具箱标准：--help 必备、默认文本输出、--json 给机器、
退出码只用 0（成功）/ 1（失败）/ 2（用法错误）/ 3（未就绪）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from lib import app_bundle, icon_builder, profiles

EXIT_OK = profiles.EXIT_OK
EXIT_FAIL = profiles.EXIT_FAIL
EXIT_USAGE = profiles.EXIT_USAGE
EXIT_NOT_READY = profiles.EXIT_NOT_READY


def _add_bundle_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-bundle", action="store_true", help="在 ~/Applications 下生成带彩色图标的 macOS .app 启动器")
    parser.add_argument("--desktop-shortcut", action="store_true", help="在 ~/Desktop 创建指向 .app 启动器的桌面快捷图标（隐含 --app-bundle）")
    parser.add_argument("--bundle-name", help=".app 启动器显示名称（默认取 --alias，如 agy-app、agy-app-ultra）")
    parser.add_argument(
        "--icon-color",
        choices=tuple(sorted(icon_builder.COLOR_PALETTES)),
        default="blue",
        help="彩色图标主题色（默认 blue）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup_desktop_profile",
        description="创建或维护 Antigravity 2.0 / IDE 同款桌面 App 多开隔离环境与启动入口",
        epilog=(
            "示例:\n"
            "  python3 <skill-root>/scripts/setup_desktop_profile.py --kind app --name acc2 --dry-run\n"
            "  python3 <skill-root>/scripts/setup_desktop_profile.py --kind app --name ultra --alias agy-app-ultra --icon-color purple --app-bundle --desktop-shortcut\n"
            "  python3 <skill-root>/scripts/setup_desktop_profile.py --kind ide --name work --write-shell --update-zshrc"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--kind", choices=("app", "ide"), help="桌面端类型：app=Antigravity 2.0，ide=Antigravity IDE")
    parser.add_argument("--name", help="隔离实例标识 slug（如 acc2、work、ultra）")
    parser.add_argument("--alias", dest="alias_name", help="Shell 启动别名（默认 agy-app-<name> 或 agy-ide-<name>）")
    parser.add_argument("--app-path", help="自定义 .app 路径（默认 /Applications/Antigravity.app 或 Antigravity IDE.app）")
    parser.add_argument("--home", help="指定真实 HOME 目录（默认读取当前用户 HOME）")
    parser.add_argument("--isolate-extensions", action="store_true", help="仅对 ide 有效：改为每个实例独立扩展目录")
    parser.add_argument("--link-dotfiles", default=".gitconfig,.ssh", help="软链进隔离 HOME 的逗号分隔项（默认 .gitconfig,.ssh）")
    _add_bundle_options(parser)
    parser.add_argument("--write-shell", action="store_true", help="将启动别名写入 ~/.config/antigravity-multi/profiles.zsh")
    parser.add_argument("--update-zshrc", action="store_true", help="在 ~/.zshrc 中追加受管 source 块（需配合 --write-shell）")
    parser.add_argument("--require-installed", action="store_true", help="若目标 .app 未安装则返回退出码 3（未就绪）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划动作，不修改任何文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印进度")
    parser.add_argument("--self-test", action="store_true", help="在临时目录运行内置自测后退出")
    return parser


def log(args: argparse.Namespace, message: str) -> None:
    if args.verbose:
        print(message, file=sys.stderr)


def link_optional_dotfiles(
    real_home: Path,
    profile_home: Path,
    dotfiles_csv: str,
    dry_run: bool,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> None:
    for raw in dotfiles_csv.split(","):
        item = raw.strip()
        if not item:
            continue
        if "/" in item or item in (".", ".."):
            warnings.append(f"已忽略非法 dotfile 项: {item}")
            continue
        src = real_home / item
        if not src.exists():
            continue
        res = profiles.ensure_symlink(profile_home / item, src, dry_run, actions)
        if res["status"] == "conflict":
            warnings.append(f"隔离 HOME 中已存在冲突项，已跳过软链: {profile_home / item}")


def prepare_desktop_fs(
    home: Path,
    paths: dict[str, Path | None],
    args: argparse.Namespace,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> None:
    profile_home = paths["profile_home"]
    gemini_dir = paths["gemini_dir"]
    config_link = paths["config_link"]
    user_data_dir = paths["user_data_dir"]
    assert profile_home and gemini_dir and config_link and user_data_dir
    profiles.ensure_dir(gemini_dir, args.dry_run, actions)
    profiles.ensure_dir(user_data_dir, args.dry_run, actions)
    global_cfg = home / ".gemini" / "config"
    if global_cfg.is_dir():
        res = profiles.ensure_symlink(config_link, global_cfg, args.dry_run, actions)
        if res["status"] == "conflict":
            warnings.append(f".gemini/config 已存在非匹配项，请手工核对: {config_link}")
    else:
        warnings.append(f"未找到全局共享配置目录 ({global_cfg})，已跳过 .gemini/config 软链")
    link_optional_dotfiles(home, profile_home, args.link_dotfiles, args.dry_run, actions, warnings)


def apply_desktop_shell(
    home: Path,
    block_id: str,
    shell_lines: list[str],
    args: argparse.Namespace,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> Path:
    profiles_zsh = home / profiles.PROFILES_ZSH_REL
    if args.write_shell:
        profiles.upsert_managed_block(profiles_zsh, block_id, shell_lines, args.dry_run, actions)
        if args.update_zshrc:
            profiles.ensure_zshrc_source(home, profiles_zsh, args.dry_run, actions)
    elif args.update_zshrc:
        warnings.append("未启用 --write-shell，已忽略 --update-zshrc")
    return profiles_zsh


def build_desktop_result(
    args: argparse.Namespace,
    slug: str,
    alias_name: str,
    app_path: str,
    app_installed: bool,
    paths: dict[str, Path | None],
    ext_dir: Path | None,
    profiles_zsh: Path,
    shell_lines: list[str],
    bundle_info: dict[str, object] | None,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> dict[str, object]:
    spec = profiles.DESKTOP_APPS[args.kind]
    profile_home, user_data_dir, launcher_path = paths["profile_home"], paths["user_data_dir"], paths["launcher_path"]
    return {
        "ok": True,
        "tool": "setup_desktop_profile",
        "dry_run": bool(args.dry_run),
        "kind": args.kind,
        "profile": slug,
        "alias": alias_name,
        "app_path": app_path,
        "app_installed": app_installed,
        "profile_home": str(profile_home),
        "user_data_dir": str(user_data_dir),
        "extensions_dir": str(ext_dir) if ext_dir else None,
        "launcher_path": str(launcher_path),
        "app_bundle": bundle_info,
        "profiles_zsh": str(profiles_zsh),
        "shell_snippet": "\n".join(shell_lines),
        "actions": actions,
        "warnings": warnings,
        "next_steps": [
            f"双击桌面/启动台图标或直接运行 {launcher_path}（Shell 别名 `{alias_name}`）",
            f"首次登录完成后，确认令牌写入 {profile_home}/.gemini/{spec['gemini_subdir']}/antigravity-oauth-token 且主实例未被登出",
        ],
    }


def _parse_validated_names(args: argparse.Namespace) -> tuple[str, str, str]:
    slug = profiles.validate_profile_name(args.name)
    spec = profiles.DESKTOP_APPS[args.kind]
    alias_name = profiles.validate_alias_name(args.alias_name or f"{spec['alias_prefix']}{slug}")
    bundle_name = app_bundle.validate_bundle_name(args.bundle_name or alias_name)
    return slug, alias_name, bundle_name


def run(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    if not args.kind or not args.name:
        return EXIT_USAGE, {"ok": False, "error": "缺少必填参数 --kind 或 --name"}
    try:
        slug, alias_name, bundle_name = _parse_validated_names(args)
    except ValueError as exc:
        return EXIT_USAGE, {"ok": False, "error": str(exc)}

    spec = profiles.DESKTOP_APPS[args.kind]
    home = profiles.resolve_home(args.home)
    app_path = args.app_path or str(spec["default_app_path"])
    app_installed = Path(app_path).is_dir()
    if args.require_installed and not app_installed:
        return EXIT_NOT_READY, {"ok": False, "error": f"目标桌面应用未安装: {app_path}", "install_command": f"brew install --cask {spec['brew_cask']}"}

    paths = profiles.desktop_paths(home, args.kind, slug)
    profile_home, user_data_dir, launcher_path = paths["profile_home"], paths["user_data_dir"], paths["launcher_path"]
    assert profile_home and user_data_dir and launcher_path
    ext_dir = None if args.isolate_extensions else paths["shared_extensions_dir"]
    actions, warnings = [], []
    log(args, f"setup_desktop_profile: kind={args.kind} slug={slug} dry_run={args.dry_run}")
    prepare_desktop_fs(home, paths, args, actions, warnings)
    launcher_body = profiles.render_desktop_launcher(args.kind, app_path, profile_home, user_data_dir, ext_dir)
    profiles.write_executable(launcher_path, launcher_body, args.dry_run, actions)
    bundle_info = None
    if args.app_bundle or args.desktop_shortcut:
        bundle_info = app_bundle.create_app_bundle(
            home, args.kind, slug, bundle_name, launcher_path, args.icon_color,
            Path(app_path), bool(args.desktop_shortcut), bool(args.dry_run), actions, warnings,
        )
    shell_lines = profiles.render_desktop_shell_lines(alias_name, launcher_path)
    profiles_zsh = apply_desktop_shell(home, f"desktop-{args.kind}-{slug}", shell_lines, args, actions, warnings)
    if not app_installed:
        warnings.append(f"当前未检测到 {app_path}，运行前请先安装: brew install --cask {spec['brew_cask']}")
    return EXIT_OK, build_desktop_result(
        args, slug, alias_name, app_path, app_installed, paths, ext_dir,
        profiles_zsh, shell_lines, bundle_info, actions, warnings,
    )


def format_text(result: dict[str, object]) -> str:
    if not result.get("ok"):
        msg = f"ERROR: {result.get('error', 'unknown error')}"
        if result.get("install_command"):
            msg += f"\n安装命令: {result['install_command']}"
        return msg
    mode = "[DRY-RUN] " if result.get("dry_run") else ""
    lines = [
        f"{mode}桌面端 ({result['kind']}) 隔离实例 '{result['profile']}' 就绪",
        f"  App 路径: {result['app_path']} ({'已安装' if result['app_installed'] else '未安装'})",
        f"  隔离 HOME: {result['profile_home']}",
        f"  User Data Dir: {result['user_data_dir']}",
        f"  启动脚本: {result['launcher_path']}",
        f"  命令别名: {result['alias']}",
    ]
    bundle = result.get("app_bundle")
    if isinstance(bundle, dict):
        lines.append(f"  桌面 App 启动器: {bundle['bundle_path']} (颜色={bundle['icon_color']})")
        if bundle.get("desktop_shortcut"):
            lines.append(f"  桌面快捷方式: {bundle['desktop_shortcut']}")
    lines.append("动作:")
    lines.extend(f"  - {a['action']} [{a['status']}]: {a['path']}" for a in result["actions"])  # type: ignore[index]
    lines.append("Shell 配置片段:")
    lines.extend(f"  {s}" for s in str(result["shell_snippet"]).splitlines())
    if result["warnings"]:
        lines.append("提示:")
        lines.extend(f"  - [WARN] {w}" for w in result["warnings"])  # type: ignore[index]
    return "\n".join(lines)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gemini" / "config").mkdir(parents=True)
        (root / ".gitconfig").write_text("[user]\nname = test\n", encoding="utf-8")
        args = build_parser().parse_args(
            ["--kind", "app", "--name", "acc2", "--home", str(root), "--write-shell", "--update-zshrc"]
        )
        code, result = run(args)
        launcher = Path(str(result["launcher_path"]))
        ok = (
            code == EXIT_OK
            and bool(result.get("ok"))
            and launcher.is_file()
            and (root / ".agy-profiles" / "app-acc2" / ".gemini" / "config").is_symlink()
            and (root / ".agy-profiles" / "app-acc2" / ".gitconfig").is_symlink()
        )
        return EXIT_OK if ok else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    code, result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))
    return code


if __name__ == "__main__":
    sys.exit(main())
