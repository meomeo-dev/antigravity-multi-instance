# 常见坑点与排障清单

> 执行到「排障」「审计告警处理」或「首次验证桌面端多开」时加载。  
> **来源**：macOS `open` 命令机制实测、Antigravity CLI 多账号运行记录及公开排障资料。  
> **核验日期**：2026-11-22（随客户端更新可能变化，排障时先运行 `inspect_instances.py` 获取当次快照）。

## 1. `SSH_CONNECTION=1 open -n -a ...` 不生效

- **原因**：macOS 的 `open` 通过 LaunchServices 启动 GUI 应用，**不会**把命令行前缀里的环境变量透传给目标 `.app` 进程。
- **表现**：新开的桌面实例仍然读写 macOS Keychain，登录第二个账号会把主实例踢下线。
- **正确写法**：使用 macOS 原生支持的 `open --env` 参数传递环境变量，由 `setup_desktop_profile.py` 生成的启动脚本已固化此写法：
  ```bash
  open -n -a "/Applications/Antigravity.app" \
    --env SSH_CONNECTION=1 \
    --env HOME="$HOME/.agy-profiles/app-acc2" \
    --args --user-data-dir="$HOME/Library/Application Support/Antigravity-acc2"
  ```

## 2. 只传 `--user-data-dir` 导致桌面端多账号互相冲突

- **原因**：`--user-data-dir` 只隔离了 Electron/VS Code 层的 `Application Support` 目录，内置后端（Language Server / Agent Hub）仍会读写 `$HOME/.gemini/antigravity`（或 `antigravity-ide`）。
- **表现**：两个同款桌面端共享同一个 `conversation_summaries.db` 与回退后的 `antigravity-oauth-token`，出现会话互相覆盖或数据库锁冲突。
- **修复**：同时传入 `--env HOME=<独立隔离目录>` 与 `--args --user-data-dir=<独立目录>`，并将 `<独立隔离目录>/.gemini/config` 软链回真实 `$HOME/.gemini/config`。

## 3. 桌面端使用隔离 `HOME` 的副作用与缓解

- **表现**：在该桌面实例内打开内置终端时，`~` 与 `$HOME` 指向 `$HOME/.agy-profiles/<kind>-<name>`，而非真实用户主目录。
- **缓解**：
  1. `setup_desktop_profile.py` 默认将真实 `.gitconfig`、`.ssh` 软链进隔离 `HOME`（可通过 `--link-dotfiles` 增删，例如追加 `.zshrc` 或 `.npmrc`）。
  2. 在桌面端打开项目仓库时，使用真实绝对路径（如 `/Users/<user>/...`），不要把代码仓库放在隔离 `HOME` 下。
  3. 若项目强依赖默认 `$HOME` 下的大量工具链缓存且不想维护软链，改用「跨形态并存（方案 B）」或「独立 macOS 系统用户（方案 D）」。

## 4. 主账号与额外账号争抢 macOS Keychain

- **原因**：不带 `SSH_CONNECTION=1` 启动的任意客户端都会读写系统 Keychain 单一槽位。
- **原则**：整台机器上**最多只让 1 个主实例**走默认 Keychain（例如默认 `agy` 或主力桌面端），其他所有账号实例一律带 `SSH_CONNECTION=1` 走各自的本地 `antigravity-oauth-token`。
- **认证死循环排查**：若某个走 Keychain 的默认实例陷入反复弹出登录或 `Authentication Required` 循环，可检查系统钥匙串中残留的 `"Antigravity Safe Storage"` 或 `gemini`/`antigravity` 条目，确认归属后由用户手工清理再重新登录（切勿由脚本未经确认擅自删除用户钥匙串项）。

## 5. 多实例并发编辑同一 Git 仓库

- **原因**：多个 CLI 或桌面端同时操作同一个工作树，极易互相覆盖未提交修改。
- **做法**：用 `git worktree add ../<repo>-wt-<profile> <branch>` 为每个并发客户端分配独立目录，避免文件竞争。

## 6. 桌面端首次验证检查清单（当本机刚安装 App 时）

在安装 `Antigravity.app` 或 `Antigravity IDE.app` 后，按以下顺序做一次实跑确认：

1. 启动主实例并确认已登录账号 A。
2. 运行 `setup_desktop_profile.py --kind <app|ide> --name acc2 --write-shell` 生成隔离环境与启动脚本。
3. 执行生成的启动脚本，验证新窗口独立弹出且未把主窗口切到前台替代。
4. 在新窗口登录账号 B，确认：
   - `<profile_home>/.gemini/<antigravity|antigravity-ide>/` 下已生成独立的 `conversation_summaries.db` 与 `antigravity_state.pbtxt`（或 `antigravity-oauth-token`），且 `<user_data_dir>` 下已生成独立的 `SingletonLock` 与会话存储；
   - 主窗口账号 A 仍保持登录状态且对话列表未与账号 B 混杂；
   - 全局 `$HOME/.gemini/config/` 中的 rules / MCP / skills 在新窗口可见。
5. 若发现 Finder 桌面图标未立即刷新，可执行 `touch ~/Applications/<name>.app` 或重新执行 `setup_desktop_profile.py`（脚本会自动调用 `lsregister -f` 刷新 LaunchServices 图标缓存）。
6. 若新版客户端更改了环境变量或数据路径，向用户汇报实测现象并在作者源目录更新本技能。
