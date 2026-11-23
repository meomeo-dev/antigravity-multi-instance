# antigravity-multi-instance

一个面向 macOS 的 Agent Skill：用于创建、盘点与维护**多个 Antigravity CLI（`agy`）账号**以及**同款 Antigravity 桌面客户端（`Antigravity.app` / `Antigravity IDE.app`）多开隔离环境**，并可生成带颜色区分的 macOS `.app` 启动器与桌面快捷图标。入口说明见 [`SKILL.md`](SKILL.md)，架构与排障细节在 `references/`。

## 功能概览

- **本机盘点与冲突审计**（`scripts/inspect_instances.py`）：只读扫描已安装的 CLI / 桌面端、现有隔离目录、受管 `.app` 启动器与 Shell 别名，检测损坏软链和 `open` 环境变量传递反模式，不读取任何令牌内容。
- **多 `agy` CLI 账号管理**（`scripts/setup_cli_profile.py`）：通过 `SSH_CONNECTION=1 agy --app_data_dir=antigravity-cli-<name>` 隔离本地 OAuth 令牌与会话状态，自动软链共享 `skills` 并输出受管 Shell 片段。
- **同款桌面 App 多开与彩色图标**（`scripts/setup_desktop_profile.py`）：组合 `open -n -a ... --env SSH_CONNECTION=1 --env HOME=... --args --user-data-dir=...` 隔离 Electron/VS Code 数据、后端 `~/.gemini/` 目录与 Keychain 凭据，同时软链共享 `~/.gemini/config/`；可选生成带 8 种配色外框与角标的 `~/Applications/<name>.app` 启动器及桌面快捷方式。

## 运行要求

- macOS（桌面端多开与 `.icns` 图标编译依赖系统自带的 `open --env`、`iconutil`、`sips`）。
- Python 3.9 或更新版本。全部脚本仅使用标准库，无需安装第三方包。

## 安装

把仓库克隆到宿主的 Skill 目录，目录名保持 `antigravity-multi-instance`。以 Antigravity 全局共享目录为例，固定到发布标签：

```sh
git clone --branch v1.0.0 --depth 1 \
  https://github.com/meomeo-dev/antigravity-multi-instance.git \
  ~/.gemini/config/skills/antigravity-multi-instance
```

常见宿主的目录：

| 宿主 | 用户级 | 项目级 |
| --- | --- | --- |
| Antigravity（CLI & 桌面端共享） | `~/.gemini/config/skills/` | `.agents/skills/` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | `.agents/skills/` |

## 快速使用

```sh
# 1. 盘点当前本机 Antigravity 客户端与多实例状态
python3 scripts/inspect_instances.py

# 2. 预览新增独立 agy CLI 账号（不改文件）
python3 scripts/setup_cli_profile.py --name acc3 --alias agy3 --write-shell --dry-run

# 3. 创建带彩色桌面图标的 Antigravity 2.0 双开启动器（蓝 / 紫金）
python3 scripts/setup_desktop_profile.py \
  --kind app --name main --alias agy-app --bundle-name agy-app \
  --icon-color blue --app-bundle --desktop-shortcut --write-shell

python3 scripts/setup_desktop_profile.py \
  --kind app --name ultra --alias agy-app-ultra --bundle-name agy-app-ultra \
  --icon-color purple --app-bundle --desktop-shortcut --write-shell
```

可选图标配色：`blue`、`purple`、`green`、`orange`、`red`、`teal`、`gold`、`slate`。

## 验证

```sh
python3 -m unittest discover -s tests -v
```

## 版本

版本遵循语义化版本（Semantic Versioning），每个发布对应一个 `vX.Y.Z` 标签。当前版本 `1.0.0`。

## 许可证

[Apache License 2.0](LICENSE)。
