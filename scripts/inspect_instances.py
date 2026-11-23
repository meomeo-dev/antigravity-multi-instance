#!/usr/bin/env python3
"""盘点本机 Antigravity 客户端安装、CLI 与桌面端多实例配置及冲突风险

Skill: antigravity-multi-instance。遵守工具箱标准：--help 必备、默认文本输出、--json 给机器、
退出码只用 0（成功）/ 1（失败）/ 2（用法错误）/ 3（未就绪）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from lib import profiles

EXIT_OK = profiles.EXIT_OK
EXIT_FAIL = profiles.EXIT_FAIL
EXIT_USAGE = profiles.EXIT_USAGE
EXIT_NOT_READY = profiles.EXIT_NOT_READY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect_instances",
        description="盘点本机 Antigravity 客户端安装、CLI 与桌面端多实例配置及冲突风险",
        epilog=(
            "示例:\n"
            "  python3 <skill-root>/scripts/inspect_instances.py\n"
            "  python3 <skill-root>/scripts/inspect_instances.py --json\n"
            "  python3 <skill-root>/scripts/inspect_instances.py --home /tmp/test-home --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--home", help="指定待检查的 HOME 目录（默认读取当前用户 HOME）")
    parser.add_argument(
        "--applications-dir",
        default="/Applications",
        help="macOS 应用程序目录（默认 /Applications）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印进度")
    parser.add_argument("--self-test", action="store_true", help="在临时目录运行内置自测后退出")
    return parser


def log(args: argparse.Namespace, message: str) -> None:
    if args.verbose:
        print(message, file=sys.stderr)


def collect_warnings(
    cli_list: list[dict[str, object]],
    desktop_list: list[dict[str, object]],
    shell_warnings: list[str],
    global_config: Path,
) -> list[str]:
    warnings = list(shell_warnings)
    if not global_config.is_dir():
        warnings.append(f"未检测到全局共享配置目录: {global_config}")
    for item in cli_list:
        skills = item.get("skills", {})
        if isinstance(skills, dict) and skills.get("broken"):
            warnings.append(f"CLI 配置 {item['dir_name']} 的 skills 软链已损坏: {skills.get('target')}")
    for item in desktop_list:
        cfg = item.get("config_symlink", {})
        if isinstance(cfg, dict) and (cfg.get("type") != "symlink" or cfg.get("broken")):
            warnings.append(f"桌面配置 {item['profile_dir']} 缺少有效的 .gemini/config 共享软链")
        if not item.get("launcher_ready"):
            warnings.append(f"桌面配置 {item['profile_dir']} 缺少可执行启动脚本: {item['launcher_path']}")
    return warnings


def inspect_global_config(home: Path) -> dict[str, object]:
    cfg = home / ".gemini" / "config"
    return {
        "path": str(cfg),
        "exists": cfg.is_dir(),
        "items": {
            "rules": (cfg / "rules").is_dir(),
            "skills": (cfg / "skills").is_dir(),
            "agents": (cfg / "agents").is_dir(),
            "mcp_config": (cfg / "mcp_config.json").is_file(),
        },
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    home = profiles.resolve_home(args.home)
    apps_dir = Path(args.applications_dir).expanduser()
    log(args, f"inspect_instances: home={home} apps_dir={apps_dir}")
    installations = profiles.detect_installations(apps_dir)
    cli_list = profiles.inspect_cli_profiles(home)
    desktop_list = profiles.inspect_desktop_profiles(home)
    bundles = profiles.find_managed_app_bundles(home)
    aliases, shell_warnings = profiles.scan_shell_definitions(home)
    global_cfg = inspect_global_config(home)
    warnings = collect_warnings(cli_list, desktop_list, shell_warnings, Path(str(global_cfg["path"])))
    return {
        "ok": True,
        "tool": "inspect_instances",
        "home": str(home),
        "installations": installations,
        "global_config": global_cfg,
        "cli_profiles": cli_list,
        "desktop_profiles": desktop_list,
        "launcher_bundles": bundles,
        "shell_aliases": aliases,
        "warnings": warnings,
    }


def format_text(result: dict[str, object]) -> str:
    lines = [f"HOME: {result['home']}"]
    inst = result["installations"]
    assert isinstance(inst, dict)
    lines.append("已安装客户端:")
    lines.append(f"  - agy CLI: {'已安装' if inst['cli']['installed'] else '未安装'} ({inst['cli']['path'] or '-'})")
    lines.append(f"  - Antigravity 2.0: {'已安装' if inst['desktop_app']['installed'] else '未安装'} ({inst['desktop_app']['path']})")
    lines.append(f"  - Antigravity IDE: {'已安装' if inst['desktop_ide']['installed'] else '未安装'} ({inst['desktop_ide']['path']})")
    cli_list = result["cli_profiles"]
    assert isinstance(cli_list, list)
    lines.append(f"CLI 实例 ({len(cli_list)}):")
    for item in cli_list:
        skills_type = item["skills"]["type"]
        model = item["settings"].get("model") or "-"
        lines.append(
            f"  - {item['dir_name']}: auth={item['auth_storage']}, skills={skills_type}, model={model}"
        )
    desk_list = result["desktop_profiles"]
    assert isinstance(desk_list, list)
    lines.append(f"桌面端隔离实例 ({len(desk_list)}):")
    for item in desk_list:
        backend_state = "initialized" if item.get("backend_dir_present") else "fresh"
        ud_state = "initialized" if item.get("user_data_initialized") else "empty"
        lines.append(
            f"  - {item['profile_dir']} ({item['kind']}): config_link={item['config_symlink']['type']}, "
            f"backend={backend_state}, user_data={ud_state}, launcher={'ready' if item['launcher_ready'] else 'missing'}"
        )
    bundles = result.get("launcher_bundles", [])
    assert isinstance(bundles, list)
    if bundles:
        lines.append(f"受管 .app 启动器 ({len(bundles)}):")
        for b in bundles:
            sc = b["desktop_shortcut"]["type"]
            lines.append(f"  - {b['name']}.app: icon={'ok' if b['has_icon'] else 'missing'}, desktop={sc}")
    warnings = result["warnings"]
    assert isinstance(warnings, list)
    lines.append(f"风险告警 ({len(warnings)}):")
    for w in warnings:
        lines.append(f"  - [WARN] {w}")
    return "\n".join(lines)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gemini" / "config").mkdir(parents=True)
        (root / ".gemini" / "antigravity-cli" / "skills").mkdir(parents=True)
        args = build_parser().parse_args(["--home", str(root), "--applications-dir", str(root / "Apps")])
        result = run(args)
        ok = bool(result.get("ok")) and len(result["cli_profiles"]) == 1
        return EXIT_OK if ok else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))
    return EXIT_OK if result.get("ok") else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
