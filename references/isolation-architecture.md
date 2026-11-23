# Antigravity 多实例隔离架构与路径矩阵

> 执行到「方案选型」「新增/排查实例路径」或「确认共享与隔离边界」时加载。  
> **来源**：Homebrew Cask 官方元数据（`brew info --json=v2 --cask antigravity antigravity-ide antigravity-cli`）、macOS `open` 手册与 Antigravity CLI 实测行为。  
> **核验日期**：2026-11-22（版本与路径属快照，随客户端升级可能变化，以当次 `inspect_instances.py` 与 `brew info` 查询为准）。

## 1. 三层冲突与隔离模型

在同一台 macOS 上并发运行多个 Antigravity 账号时，需要同时控制三层共享资源：

| 冲突层 | 默认位置 / 机制 | 不隔离时的现象 | 隔离机制 |
| :--- | :--- | :--- | :--- |
| **凭据层** | macOS Keychain 单一槽位（如 `gemini/antigravity`、`Antigravity Safe Storage`） | 新账号登录覆盖旧账号令牌，导致其他运行中实例被登出 | 传入 `SSH_CONNECTION=1`，触发后端回退为在各自 Agent 数据目录内写入本地令牌文件 `antigravity-oauth-token` |
| **Agent 数据层** | `$HOME/.gemini/<app_data_dir>`（`conversations/`、`brain/`、`conversation_summaries.db`、`settings.json`、`antigravity-oauth-token`） | SQLite 锁冲突、会话历史混杂或互相覆盖令牌 | CLI 用 `--app_data_dir=<name>`；同款桌面 App 多账号并行时为每个实例分配独立隔离 `HOME`（`$HOME/.agy-profiles/<kind>-<name>`） |
| **桌面 UI / 单实例锁层** | `$HOME/Library/Application Support/Antigravity`（或 `Antigravity IDE`）中的 `SingletonLock`、`state.vscdb`、窗口与缓存 | 再次打开 App 仅聚焦已有窗口，或 `state.vscdb` 状态互相破坏 | 使用 `open -n`（强制新建进程实例）配合 `--args --user-data-dir=<独立目录>` |

## 2. 三款官方客户端默认路径矩阵

| 产品 | Homebrew Cask | App / 命令入口 | 默认 UI 数据目录 | 默认 Agent 数据目录 |
| :--- | :--- | :--- | :--- | :--- |
| **Antigravity CLI** | `antigravity-cli` | `agy` | 无 | `$HOME/.gemini/antigravity-cli` |
| **Antigravity 2.0 桌面端** | `antigravity` | `/Applications/Antigravity.app` | `$HOME/Library/Application Support/Antigravity` | `$HOME/.gemini/antigravity` |
| **Antigravity IDE** | `antigravity-ide` | `/Applications/Antigravity IDE.app`（CLI：`agy-ide`） | `$HOME/Library/Application Support/Antigravity IDE` | `$HOME/.gemini/antigravity-ide`（扩展：`$HOME/.antigravity-ide/extensions`） |

## 3. 共享与独立数据边界

- **天然全局共享**（所有 CLI 与桌面端共用，推荐统一维护在这里）：
  - `$HOME/.gemini/config/`：`rules/`、`skills/`、`agents/`、`mcp_config.json`、`plugins/`、`sidecars/`、`config.json`。
  - 对于使用隔离 `HOME` 的桌面端实例，必须将 `<profile_home>/.gemini/config` 软链指向真实 `$HOME/.gemini/config`，才能同步全局规则、MCP 与 Skills。
- **可选软链共享**：
  - CLI 历史路径 `$HOME/.gemini/antigravity-cli/skills`：如旧 Skills 仍放在此目录，新增 CLI profile 时通过软链共享；长期建议迁到 `$HOME/.gemini/config/skills`。
  - Antigravity IDE 扩展：通过 `--extensions-dir="$HOME/.antigravity-ide/extensions"` 跨多开实例共享，避免重复安装；需要隔离扩展时改用 `--isolate-extensions`。
  - 桌面端隔离 `HOME` 内的常用点文件（如 `.gitconfig`、`.ssh`）：按需从真实 `$HOME` 软链进隔离目录。
- **严禁共享（必须按账号独立）**：
  - `antigravity-oauth-token`
  - `conversation_summaries.db`、`conversations/`、`brain/`、`*.pb`
  - `state.vscdb`、`SingletonLock`、`--user-data-dir` 指向的目录
  - `settings.json`（各账号可独立设定默认 `model`、`colorScheme`、`trustedWorkspaces`）

## 4. 四类并行架构对比

| 方案 | 适用场景 | 优点 | 限制 / 风险 |
| :--- | :--- | :--- | :--- |
| **A. 多 CLI 并行** | 日常多账号终端并发任务 | 原生无单实例锁，`SSH_CONNECTION=1 agy --app_data_dir=<name>` 已长期实测稳定 | 纯终端交互 |
| **B. 跨形态并存** | 同时用 `Antigravity.app` + `Antigravity IDE.app` + 多个 `agy` | 默认目录与 Bundle ID 天然隔离 | 最多只保留一个客户端走默认 Keychain，其余须带 `SSH_CONNECTION=1` |
| **C. 同款桌面 App 多开** | 同时运行 2+ 个 `Antigravity.app` 或 2+ 个 `Antigravity IDE.app` 登不同账号 | 单 macOS 用户内并行查看多窗口，可配彩色图标 `.app` 启动器与桌面快捷方式 | 需同时隔离 `HOME`、`--user-data-dir` 和 `SSH_CONNECTION=1`；App 内置终端中 `~` 会指向隔离 `HOME`；Antigravity 2.0（v2.34.0）已实机验证双开隔离，`Antigravity IDE.app` 首次安装后仍建议按排障清单实跑一次验收 |
| **D. 独立 macOS 系统用户** | 重度多桌面账号并行且零副作用诉求 | Keychain、`Application Support`、`HOME` 内核级彻底隔离 | 需配合快速用户切换 |

## 5. 彩色桌面图标与 `.app` 启动器结构

`setup_desktop_profile.py --app-bundle [--desktop-shortcut]` 会生成一个轻量 macOS `.app` 包装器，位置在 `$HOME/Applications/<bundle_name>.app`（可选在 `$HOME/Desktop/<bundle_name>.app` 建立软链）：

```text
$HOME/Applications/<bundle_name>.app/
└── Contents/
    ├── Info.plist                 # 独立 CFBundleIdentifier、LSUIElement=true、AppIcon.icns
    ├── MacOS/launcher             # 委托执行 $HOME/.agy-profiles/bin/<launcher>
    └── Resources/AppIcon.icns     # 基于官方 icon.icns 合成彩色外框与角标（支持 8 种配色）
```

- **内置配色**：`blue`、`purple`、`green`、`orange`、`red`、`teal`、`gold`、`slate`。
- **运行态图标说明**：彩色图标显示在桌面快捷方式、Spotlight、启动台与固定在程序坞（Dock）的启动入口；点击后通过 `open -n -a "/Applications/Antigravity.app"` 启动官方签名进程，因此活动程序坞与 `Cmd+Tab` 中仍保留官方签名图标，以保证应用签名和自动更新不受影响。建议在不同窗口内设置浅色/深色外观进一步区分。

## 6. 实机验证记录（2026-11-22）

- **Antigravity CLI（`1.5.12`）**：多套 `SSH_CONNECTION=1 agy --app_data_dir=antigravity-cli-<name>` 可并行运行，各自独立写入 `antigravity-oauth-token`（`0600`）与 `settings.json`，共享 `$HOME/.gemini/config/`。
- **Antigravity 2.0 桌面端（`2.34.0`）**：通过生成的 `.app` 启动器与默认 `Antigravity.app` 并行运行时，实测生成独立 `SingletonLock`、独立 `Application Support/Antigravity-<name>`（`app_storage.json`、`Cookies`、`Local Storage`）、独立 `$PROFILE_HOME/.gemini/antigravity/`（`conversation_summaries.db`、`antigravity_state.pbtxt`、`brain/`、`conversations/`、`daemon/`）与独立 `$PROFILE_HOME/Library/Logs/Antigravity`，且 `.gemini/config` 软链正常共享全局配置。
