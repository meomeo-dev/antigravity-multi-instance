---
name: antigravity-multi-instance
description: >-
  当用户需要在 macOS 上同时使用、创建、维护或排查多个 Antigravity CLI（agy / agy2 / agy-ultra 等）
  和多个同款 Antigravity 桌面客户端（Antigravity 2.0 `Antigravity.app` 或 `Antigravity IDE.app`）
  的多开、多账号隔离环境，或生成带颜色区分的桌面 `.app` 启动图标时使用。提供本机实例盘点与冲突审计、
  独立的 CLI `--app_data_dir` 配置创建、同款桌面端 `open -n --env SSH_CONNECTION=1 --env HOME --args --user-data-dir`
  启动器、彩色图标 `.app` 包装器、桌面快捷方式与 Shell 别名生成。
  不用于单账号安装教程、常规 Antigravity 功能问答或未经授权修改系统 Keychain。
---

# Antigravity 多实例与多账号运维（CLI + 桌面端）

本技能固化 macOS 上**多个 `agy` CLI** 与**同款 Antigravity 桌面 App 多开**的创建、维护与排障工序，使凭据（Keychain）、Agent 数据目录（`~/.gemini/`）与桌面单实例锁（`Application Support`）彻底解耦，同时共享全局 `~/.gemini/config/` 配置。

本文是**记忆唤醒索引**：只保留流程骨架、速查表、边界与指针；三层架构与排障细节在 `references/`，按步骤按需加载，不要一次全读。

## 触发与形态

出现以下任一请求时触发：

- 新增或维护多个 `agy` CLI 账号（参考 `agy` / `agy2` / `agy-ultra` 模式，隔离 `--app_data_dir` 与 OAuth 令牌）；
- 同时打开 2 个及以上**同款** Antigravity 桌面客户端（`Antigravity.app` 或 `Antigravity IDE.app`）并分别登录不同账号；
- 盘点本机已有哪些 Antigravity CLI / 桌面端实例、排查多开互踢（Keychain 覆盖）、软链损坏或 `open` 环境变量失效。

形态：以「盘点现状 → 预览计划（`--dry-run`）→ 幂等落地 → 人工登录与验收」闭环执行。不替用户执行 OAuth 浏览器登录，也不擅自删除系统 Keychain 项。

## 场景到命令速查表

> 路径约定：`<skill-root>` 指本 `SKILL.md` 所在目录；全部脚本仅依赖 Python 3.9+ 标准库，无第三方包。

| 使用场景 | 完整命令 |
| :--- | :--- |
| 盘点本机客户端安装、已有实例、Shell 别名与冲突告警 | `python3 <skill-root>/scripts/inspect_instances.py` |
| 以机器可读 JSON 盘点现状（供 Agent 决策） | `python3 <skill-root>/scripts/inspect_instances.py --json` |
| 预览新增第 N 个 `agy` CLI 账号（不改文件） | `python3 <skill-root>/scripts/setup_cli_profile.py --name acc3 --alias agy3 --write-shell --dry-run` |
| 创建新的 `agy` CLI 账号并写入受管 Shell 别名 | `python3 <skill-root>/scripts/setup_cli_profile.py --name acc3 --alias agy3 --tab-title --write-shell --update-zshrc` |
| 预览新增第 2 个 Antigravity 2.0 桌面端多开环境 | `python3 <skill-root>/scripts/setup_desktop_profile.py --kind app --name acc2 --write-shell --dry-run` |
| 创建 Antigravity 2.0 同款多开环境与带彩色桌面图标的 `.app` 启动器 | `python3 <skill-root>/scripts/setup_desktop_profile.py --kind app --name ultra --alias agy-app-ultra --icon-color purple --app-bundle --desktop-shortcut --write-shell` |
| 创建 Antigravity IDE 同款多开环境（共享扩展目录） | `python3 <skill-root>/scripts/setup_desktop_profile.py --kind ide --name work --icon-color green --app-bundle --desktop-shortcut --write-shell --update-zshrc` |
| 校验脚本回归测试（隔离临时目录，不碰真实 HOME） | `python3 -m unittest discover -s <skill-root>/tests` |

## 流程

> 节点标记：`[自动]`= 直接调用工具完成；`[主观]`= 语义判断与方案权衡；`[交互]`= 需向用户确认；`[人工]`= 必须用户亲手操作，只提示不代做。

1. **[自动] 盘点现状与冲突检测**：运行 `python3 <skill-root>/scripts/inspect_instances.py --json`，获取已安装的客户端（`agy`、`Antigravity.app`、`Antigravity IDE.app`）、现有 CLI/桌面 profile、全局 `~/.gemini/config/` 状态与 `warnings`。
2. **[主观] 选择隔离形态**：结合用户诉求与 `references/isolation-architecture.md` 决定目标类型：
   - 新增终端账号 → `setup_cli_profile.py`（走 `SSH_CONNECTION=1 agy --app_data_dir=antigravity-cli-<name>`）；
   - 新增同款桌面多开 → 确认是否已安装对应 `.app`（未安装先提示 `brew install --cask antigravity` 或 `antigravity-ide`），再使用 `setup_desktop_profile.py`（隔离 `HOME` + `--user-data-dir` + `open -n --env SSH_CONNECTION=1`）；
   - 若用户要求对桌面内置终端完全零 `~` 偏移，建议改走跨形态并存（`Antigravity.app` + `Antigravity IDE.app`）或独立 macOS 系统用户。
3. **[自动] Dry-run 预览**：先带 `--dry-run` 运行对应创建脚本，核对将创建的目录、软链、启动脚本路径与 Shell 片段，确认无 `conflict` 告警、无重复别名。
4. **[交互] 确认写入范围**：若计划修改 `~/.zshrc`（`--update-zshrc`）或新增/覆盖启动别名，向用户展示 dry-run 摘要并确认后再执行实际写入（不带 `--dry-run`）。
5. **[自动] 落地并复检**：去掉 `--dry-run` 执行创建脚本；完成后再次运行 `python3 <skill-root>/scripts/inspect_instances.py`，确认新实例出现在清单中且无损坏软链或反模式告警。
6. **[人工] 首次登录与防互踢验收**：提示用户重新加载 Shell（`source ~/.zshrc` 或 `source ~/.config/antigravity-multi/profiles.zsh`），启动新实例完成 OAuth 登录，并按 `references/troubleshooting-and-gotchas.md` 第 6 节核对：
   - 令牌已写入新实例自己的 `antigravity-oauth-token` 文件；
   - 原有主实例未被登出；
   - `~/.gemini/config/` 中的全局 rules / MCP / skills 均可见。

## 边界与安全约束

- **不读取、不打印、不复制任何凭据内容**：脚本只检查 `antigravity-oauth-token` 是否存在及权限，不触碰 token 内容与 macOS Keychain 数据。
- **不覆盖冲突路径**：目标位置已存在非匹配文件或目录时报告 `conflict` 并跳过，交给用户裁决。
- **Shell 修改受管且可回退**：别名统一写入 `~/.config/antigravity-multi/profiles.zsh` 的具名定界块（`# >>> agy-multi:<id> >>>`），`~/.zshrc` 仅在显式传 `--update-zshrc` 时追加一条受管 `source` 块，不改动用户原有手写 alias（如既有 `agy2` / `agy-ultra`）。
- **整机 Keychain 单主原则**：最多只保留 1 个主实例走默认 macOS Keychain，所有额外实例必须带 `SSH_CONNECTION=1`。

## 失败与纠正反馈

执行本技能时若某步骤失败（如新版桌面端更改了数据目录、不再识别 `SSH_CONNECTION=1` 或出现 Keychain 死循环）、或用户要求变更默认命名/目录布局：

- 先查阅 `references/troubleshooting-and-gotchas.md` 定位原因并向用户报告具体命令、退出码与现象；
- 只管本次的调整直接通过参数覆盖（如 `--alias`、`--app-path`、`--link-dotfiles`、`--isolate-extensions`）；
- 需要固化到本技能本身的新规则或兼容修复，整理具体证据后交由维护者在作者源目录更新并重新通过测试，不要修改已安装的只读副本。

## 贯穿原则

- **先盘点、再预览、后写入**：所有变更前必跑 `inspect_instances.py` 与 `--dry-run`。
- **共享归 `~/.gemini/config/`，状态严格隔离**：绝不让两个不同账号共用同一 `--app_data_dir` 或 `--user-data-dir`。
- **macOS `open` 必须用 `--env`**：禁止生成 `SSH_CONNECTION=1 open -n -a ...` 这类无法向 LaunchServices 透传变量的命令。
- **多实例并发改代码用 `git worktree`**：防止多个 CLI / 桌面端并发写同一工作目录造成覆盖。

## 指针

- `references/isolation-architecture.md` —— 三层隔离模型、CLI / Antigravity 2.0 / IDE 默认路径矩阵与四类方案对比（方案选型与路径核对时加载）。
- `references/troubleshooting-and-gotchas.md` —— `open --env` 坑点、隔离 `HOME` 副作用、Keychain 排障与桌面端首次验收清单（排障与验收时加载）。
- `scripts/inspect_instances.py` —— 盘点已安装客户端、CLI/桌面端实例、Shell 别名与风险告警。
- `scripts/setup_cli_profile.py` —— 幂等创建/维护隔离 `agy` CLI 账号目录、`skills` 软链与 Shell 启动入口。
- `scripts/setup_desktop_profile.py` —— 幂等创建/维护 Antigravity 2.0 / IDE 同款多开隔离 `HOME`、共享软链、`open -n --env` 启动脚本、彩色图标 `.app` 启动器与桌面快捷方式。
- `scripts/lib/profiles.py` —— 三个工具共享的路径解析、校验、软链与受管配置块库（不直接执行）。
- `scripts/lib/app_bundle.py` —— macOS `.app` 启动器生成与桌面快捷方式库（不直接执行）。
- `scripts/lib/icon_builder.py` —— 纯标准库彩色卡片/角标 `.icns` 图标合成库（不直接执行）。
- `tests/test_scripts.py` —— 覆盖全部工具、退出码、`--dry-run`、幂等性与反模式告警的单元测试。

执行到对应环节再加载对应 reference，不要一次全读。
