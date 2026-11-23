"""Unit tests for antigravity-multi-instance toolbox scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def run_tool(script_name: str, args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)


class ToolboxScriptsTest(unittest.TestCase):
    def test_help_and_self_test_all_tools(self) -> None:
        clean_env = {"PATH": os.environ.get("PATH", "")}
        for name in ("inspect_instances.py", "setup_cli_profile.py", "setup_desktop_profile.py"):
            with tempfile.TemporaryDirectory() as empty_home:
                env = {**clean_env, "HOME": empty_home}
                res = run_tool(name, ["--help"], env=env)
                self.assertEqual(res.returncode, 0, msg=f"{name} --help failed: {res.stderr}")
                self.assertIn("示例", res.stdout)
                self.assertEqual(list(Path(empty_home).iterdir()), [])

                st = run_tool(name, ["--self-test"], env=env)
                self.assertEqual(st.returncode, 0, msg=f"{name} --self-test failed: {st.stderr}")
                self.assertEqual(list(Path(empty_home).iterdir()), [])

    def test_setup_cli_profile_dry_run_and_apply_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".gemini" / "antigravity-cli" / "skills").mkdir(parents=True)

            dry = run_tool("setup_cli_profile.py", ["--name", "acc3", "--alias", "agy3", "--home", str(home), "--write-shell", "--update-zshrc", "--dry-run", "--json"])
            self.assertEqual(dry.returncode, 0, dry.stderr)
            dry_data = json.loads(dry.stdout)
            self.assertTrue(dry_data["dry_run"])
            self.assertFalse((home / ".gemini" / "antigravity-cli-acc3").exists())
            self.assertFalse((home / ".zshrc").exists())

            first = run_tool("setup_cli_profile.py", ["--name", "acc3", "--alias", "agy3", "--home", str(home), "--write-shell", "--update-zshrc", "--json"])
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((home / ".gemini" / "antigravity-cli-acc3" / "skills").is_symlink())
            profiles_zsh = home / ".config" / "antigravity-multi" / "profiles.zsh"
            self.assertIn("SSH_CONNECTION=1 agy --app_data_dir=antigravity-cli-acc3", profiles_zsh.read_text(encoding="utf-8"))
            self.assertIn("profiles.zsh", (home / ".zshrc").read_text(encoding="utf-8"))

            second = run_tool("setup_cli_profile.py", ["--name", "acc3", "--alias", "agy3", "--home", str(home), "--write-shell", "--update-zshrc", "--json"])
            self.assertEqual(second.returncode, 0, second.stderr)
            second_data = json.loads(second.stdout)
            statuses = {a["action"]: a["status"] for a in second_data["actions"]}
            self.assertEqual(statuses["mkdir"], "exists")
            self.assertEqual(statuses["symlink"], "exists")
            self.assertEqual(statuses["managed_block"], "unchanged")

    def test_setup_desktop_profile_require_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            missing = run_tool(
                "setup_desktop_profile.py",
                ["--kind", "app", "--name", "acc2", "--home", str(home), "--app-path", str(home / "No.app"), "--require-installed", "--json"],
            )
            self.assertEqual(missing.returncode, 3)

    def test_setup_desktop_profile_ide_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            app_bundle = home / "Apps" / "Antigravity IDE.app"
            app_bundle.mkdir(parents=True)
            (home / ".gemini" / "config").mkdir(parents=True)
            (home / ".gitconfig").write_text("[user]\nname = demo\n", encoding="utf-8")

            res = run_tool(
                "setup_desktop_profile.py",
                ["--kind", "ide", "--name", "work", "--home", str(home), "--app-path", str(app_bundle), "--write-shell", "--update-zshrc", "--json"],
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertTrue(data["app_installed"])
            launcher = Path(data["launcher_path"])
            self.assertTrue(launcher.is_file() and os.access(launcher, os.X_OK))
            script_text = launcher.read_text(encoding="utf-8")
            for token in ("open -n -a", "--env SSH_CONNECTION=1", "--env HOME=", "--user-data-dir=", "--extensions-dir="):
                self.assertIn(token, script_text)
            syntax = subprocess.run(["bash", "-n", str(launcher)], capture_output=True, text=True, check=False)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_inspect_instances_detects_profiles_and_antipatterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".gemini" / "config").mkdir(parents=True)
            (home / ".gemini" / "antigravity-cli" / "skills").mkdir(parents=True)
            acc2 = home / ".gemini" / "antigravity-cli-acc2"
            acc2.mkdir(parents=True)
            (acc2 / "antigravity-oauth-token").write_text("dummy", encoding="utf-8")
            (acc2 / "skills").symlink_to(home / ".gemini" / "missing-target")
            (home / ".zshrc").write_text(
                "alias bad-app='SSH_CONNECTION=1 open -n -a \"/Applications/Antigravity.app\" --args --user-data-dir=\"$HOME/x\"'\n",
                encoding="utf-8",
            )

            res = run_tool("inspect_instances.py", ["--home", str(home), "--applications-dir", str(home / "Apps"), "--json"])
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(len(data["cli_profiles"]), 2)
            joined_warnings = "\n".join(data["warnings"])
            self.assertIn("skills 软链已损坏", joined_warnings)
            self.assertIn("open --env SSH_CONNECTION=1", joined_warnings)
            self.assertIn("未隔离 HOME", joined_warnings)

    def test_setup_desktop_profile_colored_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".gemini" / "config").mkdir(parents=True)
            (home / "Desktop").mkdir()
            res = run_tool(
                "setup_desktop_profile.py",
                [
                    "--kind", "app", "--name", "ultra", "--alias", "agy-app-ultra",
                    "--home", str(home), "--app-bundle", "--desktop-shortcut",
                    "--icon-color", "purple", "--json",
                ],
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            bundle = Path(data["app_bundle"]["bundle_path"])
            self.assertTrue((bundle / "Contents" / "Info.plist").is_file())
            self.assertTrue((bundle / "Contents" / "MacOS" / "launcher").is_file())
            self.assertTrue((home / "Desktop" / "agy-app-ultra.app").is_symlink())
            if data["app_bundle"]["icon_meta"].get("built"):
                self.assertTrue((bundle / "Contents" / "Resources" / "AppIcon.icns").is_file())
            backend = home / ".agy-profiles" / "app-ultra" / ".gemini" / "antigravity"
            backend.mkdir(parents=True)
            (backend / "antigravity_state.pbtxt").write_text("state", encoding="utf-8")
            ud = home / "Library" / "Application Support" / "Antigravity-ultra"
            (ud / "app_storage.json").write_text("{}", encoding="utf-8")
            insp = run_tool("inspect_instances.py", ["--home", str(home), "--applications-dir", str(home / "NoApps"), "--json"])
            self.assertEqual(insp.returncode, 0, insp.stderr)
            insp_data = json.loads(insp.stdout)
            self.assertEqual(len(insp_data["launcher_bundles"]), 1)
            self.assertTrue(insp_data["desktop_profiles"][0]["state_file_present"])
            self.assertTrue(insp_data["desktop_profiles"][0]["user_data_initialized"])

    def test_invalid_names_return_usage_error(self) -> None:
        res_cli = run_tool("setup_cli_profile.py", ["--name", "../escape", "--json"])
        self.assertEqual(res_cli.returncode, 2)
        res_desk = run_tool("setup_desktop_profile.py", ["--kind", "app", "--name", "default", "--json"])
        self.assertEqual(res_desk.returncode, 2)


if __name__ == "__main__":
    unittest.main()
