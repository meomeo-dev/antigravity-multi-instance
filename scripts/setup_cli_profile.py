#!/usr/bin/env python3
"""创建或维护独立的 agy CLI 多账号配置目录、skills 软链与 Shell 启动别名

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
        prog="setup_cli_profile",
        description="创建或维护独立的 agy CLI 多账号配置目录、skills 软链与 Shell 启动别名",
        epilog=(
            "示例:\n"
            "  python3 <skill-root>/scripts/setup_cli_profile.py --name acc3 --dry-run\n"
            "  python3 <skill-root>/scripts/setup_cli_profile.py --name acc3 --alias agy3 --write-shell\n"
            "  python3 <skill-root>/scripts/setup_cli_profile.py --name work --tab-title --write-shell --update-zshrc"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--name", help="账号标识 slug（如 acc3、work、ultra），目录名为 antigravity-cli-<name>")
    parser.add_argument("--alias", dest="alias_name", help="Shell 启动别名（默认 agy-<name>）")
    parser.add_argument("--home", help="指定目标 HOME 目录（默认读取当前用户 HOME）")
    parser.add_argument("--no-skills-symlink", action="store_true", help="不创建指向主 CLI skills 目录的软链")
    parser.add_argument("--tab-title", action="store_true", help="生成带终端 Tab 标题切换的 zsh 函数而非简单 alias")
    parser.add_argument("--write-shell", action="store_true", help="写入受管配置文件 ~/.config/antigravity-multi/profiles.zsh")
    parser.add_argument("--update-zshrc", action="store_true", help="在 ~/.zshrc 中追加受管 source 块（需配合 --write-shell）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划动作，不修改任何文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印进度")
    parser.add_argument("--self-test", action="store_true", help="在临时目录运行内置自测后退出")
    return parser


def log(args: argparse.Namespace, message: str) -> None:
    if args.verbose:
        print(message, file=sys.stderr)


def apply_cli_fs(
    home: Path,
    data_dir_path: Path,
    link_skills: bool,
    dry_run: bool,
    actions: list[dict[str, object]],
    warnings: list[str],
) -> None:
    profiles.ensure_dir(data_dir_path, dry_run, actions)
    if not link_skills:
        return
    src_skills = home / ".gemini" / profiles.CLI_DEFAULT_DIR / "skills"
    if not src_skills.is_dir():
        warnings.append(f"未找到默认 CLI skills 目录 ({src_skills})，已跳过 skills 软链")
        return
    res = profiles.ensure_symlink(data_dir_path / "skills", src_skills, dry_run, actions)
    if res["status"] == "conflict":
        warnings.append(f"目标已存在非匹配路径，已跳过软链: {data_dir_path / 'skills'}")


def apply_shell_config(
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


def run(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    if not args.name:
        return EXIT_USAGE, {"ok": False, "error": "缺少必填参数 --name"}
    try:
        slug = profiles.validate_profile_name(args.name)
        alias_name = profiles.validate_alias_name(args.alias_name or f"agy-{slug}")
    except ValueError as exc:
        return EXIT_USAGE, {"ok": False, "error": str(exc)}

    home = profiles.resolve_home(args.home)
    data_dir_name, data_dir_path = profiles.cli_data_dir(home, slug)
    actions: list[dict[str, object]] = []
    warnings: list[str] = []
    log(args, f"setup_cli_profile: slug={slug} dir={data_dir_path} dry_run={args.dry_run}")

    apply_cli_fs(home, data_dir_path, not args.no_skills_symlink, args.dry_run, actions, warnings)
    shell_lines = profiles.render_cli_shell_lines(alias_name, data_dir_name, args.tab_title)
    profiles_zsh = apply_shell_config(home, f"cli-{slug}", shell_lines, args, actions, warnings)
    return EXIT_OK, {
        "ok": True,
        "tool": "setup_cli_profile",
        "dry_run": bool(args.dry_run),
        "profile": slug,
        "alias": alias_name,
        "app_data_dir": data_dir_name,
        "data_dir_path": str(data_dir_path),
        "profiles_zsh": str(profiles_zsh),
        "shell_snippet": "\n".join(shell_lines),
        "actions": actions,
        "warnings": warnings,
        "next_steps": [
            f"确保已加载 Shell 片段（或运行: source {profiles_zsh}）",
            f"首次运行 `{alias_name}` 并完成该账号的 OAuth 登录（令牌将存入 {data_dir_path}/antigravity-oauth-token）",
        ],
    }


def format_text(result: dict[str, object]) -> str:
    if not result.get("ok"):
        return f"ERROR: {result.get('error', 'unknown error')}"
    mode = "[DRY-RUN] " if result.get("dry_run") else ""
    lines = [
        f"{mode}CLI profile '{result['profile']}' 就绪",
        f"  app_data_dir: {result['app_data_dir']}",
        f"  数据目录: {result['data_dir_path']}",
        f"  命令别名: {result['alias']}",
        "动作:",
    ]
    for act in result["actions"]:  # type: ignore[index]
        lines.append(f"  - {act['action']} [{act['status']}]: {act['path']}")
    lines.append("Shell 配置片段:")
    lines.extend(f"  {s}" for s in str(result["shell_snippet"]).splitlines())
    if result["warnings"]:
        lines.append("提示:")
        lines.extend(f"  - [WARN] {w}" for w in result["warnings"])  # type: ignore[index]
    return "\n".join(lines)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gemini" / "antigravity-cli" / "skills").mkdir(parents=True)
        args = build_parser().parse_args(
            ["--name", "acc3", "--alias", "agy3", "--home", str(root), "--write-shell", "--update-zshrc"]
        )
        code, result = run(args)
        ok = (
            code == EXIT_OK
            and bool(result.get("ok"))
            and (root / ".gemini" / "antigravity-cli-acc3" / "skills").is_symlink()
            and (root / profiles.PROFILES_ZSH_REL).is_file()
            and (root / ".zshrc").is_file()
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
