"""The installer and the Mac starter: on a Mac without Apple's developer tools, it waits for them."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install.sh"
STARTER = ROOT / "scripts" / "starter" / "Lakeba OS.command"
ZIP = ROOT / "docs" / "downloads" / "Lakeba-OS-mac.zip"

# Stand-ins for a Mac: uname says Darwin, xcode-select and pgrep follow a scripted install window,
# and git answers --version but fails anything else, so the run stops right after the developer tools.
FAKES = {
    "uname": 'echo Darwin\n',
    "xcode-select": '''case "$1" in
  -p) [ -f "$FAKE_STATE/installed" ] && echo /Library/Developer/CommandLineTools && exit 0; exit 2 ;;
  --install) touch "$FAKE_STATE/requested" ;;
esac
''',
    # The window stays open for FAKE_OPEN checks, then closes: with the tools in (FAKE_RESULT=installed)
    # or without them (cancelled). FAKE_OPEN=0 means no window ever appears.
    "pgrep": '''n=$(( $(cat "$FAKE_STATE/checks" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_STATE/checks"
[ "$n" -le "$FAKE_OPEN" ] && exit 0
[ "$FAKE_RESULT" = installed ] && touch "$FAKE_STATE/installed"
exit 1
''',
    "git": '[ "$1" = --version ] && echo "git version 2.50.0" && exit 0\nexit 1\n',
}


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class DeveloperToolsTest(unittest.TestCase):
    def run_install(self, result, open_checks=3, starter=False, wait=600):
        tmp = Path(tempfile.mkdtemp(prefix="agent-team-install-test-"))
        bin_dir, state = tmp / "bin", tmp / "state"
        bin_dir.mkdir(); state.mkdir()
        for name, body in FAKES.items():
            (bin_dir / name).write_text("#!/bin/sh\n" + body)
            (bin_dir / name).chmod(0o755)
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp / "home"),
               "AGENT_TEAM_HOME": str(tmp / "at"), "BIN_DIR": str(tmp / "bin-out"),
               "AGENT_TEAM_SOURCE": str(tmp / "no-such-repo"), "AGENT_TEAM_NO_UV": "1",
               "AGENT_TEAM_CLT_POLL": "0", "AGENT_TEAM_CLT_WAIT": str(wait),
               "FAKE_STATE": str(state), "FAKE_OPEN": str(open_checks), "FAKE_RESULT": result}
        env.pop("LAKEBA_OS_STARTER", None)
        if starter:
            env["LAKEBA_OS_STARTER"] = "1"
        out = subprocess.run(["bash", str(INSTALL), "--no-plugin", "--no-rea", "--no-ui", "--no-shortcut"],
                             env=env, capture_output=True, text=True, timeout=60)
        self.assertTrue((state / "requested").exists(), "asks macOS to install the developer tools")
        return out.stdout + out.stderr

    def test_waits_for_the_install_then_carries_on(self):
        out = self.run_install("installed")
        self.assertIn("waiting for Apple's developer tools to finish installing", out)
        self.assertIn("developer tools are installed: carrying on", out)
        self.assertNotIn("run this again", out)
        self.assertNotIn("weren't installed", out)
        # It went on past git, to the Python check or the download (which the stand-in git fails).
        self.assertTrue("using " in out or "needs Python 3.11" in out, out)

    def test_cancel_says_what_to_do(self):
        out = self.run_install("cancelled")
        self.assertIn("weren't installed (the window was closed, or Cancel was clicked)", out)
        self.assertIn("run this installer again", out)
        self.assertNotIn("carrying on", out)

    def test_cancel_from_the_starter_says_double_click(self):
        out = self.run_install("cancelled", starter=True)
        self.assertIn("double-click Lakeba OS again", out)

    def test_no_window_gives_a_hint_then_times_out(self):
        out = self.run_install("never", open_checks=0, wait=200)
        self.assertIn("No window to install them?", out)
        self.assertIn("still not installed after 3 minutes", out)
        self.assertNotIn("carrying on", out)

    def test_developer_tools_come_before_python(self):
        # On a Mac without them, running python3 opens the same install window, so look for Python after.
        text = INSTALL.read_text()
        self.assertLess(text.index('xcode-select --install'), text.index('for c in python3.13'))


class StarterTest(unittest.TestCase):
    def test_starter_marks_itself_for_the_installer(self):
        self.assertIn("| LAKEBA_OS_STARTER=1 bash", STARTER.read_text())

    def test_zip_holds_the_current_starter_and_keeps_it_executable(self):
        with zipfile.ZipFile(ZIP) as z:
            info = z.getinfo("Lakeba OS.command")
            self.assertEqual(z.read(info), STARTER.read_bytes(), "rebuild docs/downloads/Lakeba-OS-mac.zip")
            self.assertTrue((info.external_attr >> 16) & stat.S_IXUSR, "the starter must stay executable")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class PathNoteTest(unittest.TestCase):
    """Lakeba OS runs agent-team by its full path: from the starter, ~/.local/bin off PATH needs no word."""

    def note(self, starter, on_path=False, profile=""):
        text = INSTALL.read_text()
        start = text.index("path_note() {")
        func = text[start:text.index("\n}\n", start) + 3]
        home = Path(tempfile.mkdtemp(prefix="agent-team-path-test-"))
        (home / ".profile").write_text(profile)
        bin_dir = home / ".local" / "bin"
        path = f"{bin_dir}:/usr/bin:/bin" if on_path else "/usr/bin:/bin"
        env = {"HOME": str(home), "PATH": path, "BIN_DIR": str(bin_dir)}
        if starter:
            env["LAKEBA_OS_STARTER"] = "1"
        script = ("say() { echo \"==> $*\"; }\nwarn() { echo \"! $*\"; }\n" + func + "path_note\n")
        out = subprocess.run(["/bin/bash", "-c", script], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout + out.stderr

    def test_starter_says_nothing_about_path(self):
        self.assertEqual(self.note(starter=True), "")

    def test_terminal_install_gives_the_export_line(self):
        out = self.note(starter=False)
        self.assertIn("is not on your PATH", out)
        self.assertIn('export PATH="', out)

    def test_terminal_install_on_debian_says_open_a_new_terminal(self):
        out = self.note(starter=False, profile='PATH="$HOME/.local/bin:$PATH"\n')
        self.assertIn("open a new terminal", out)
        self.assertNotIn("export PATH", out)

    def test_already_on_path_says_nothing(self):
        self.assertEqual(self.note(starter=False, on_path=True), "")


@unittest.skipUnless(shutil.which("osacompile") and shutil.which("plutil"), "needs macOS")
class AppNameTest(unittest.TestCase):
    """The Local Network prompt names the app: Lakeba OS, not osacompile's "applet", and says why."""

    def test_applet_is_named_and_says_why_it_scans(self):
        import plistlib
        text = INSTALL.read_text()
        start = text.index("name_app() {")
        func = text[start:text.index("\n}\n", start) + 3]
        app = Path(tempfile.mkdtemp(prefix="agent-team-app-test-")) / "Lakeba OS.app"
        subprocess.run(["osacompile", "-o", str(app), "-e", 'do shell script "true"'], check=True,
                       capture_output=True, timeout=60)
        out = subprocess.run(["/bin/bash", "-c", func + 'name_app "$1"', "-", str(app)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleName"], "Lakeba OS")
        self.assertEqual(info["CFBundleDisplayName"], "Lakeba OS")
        self.assertEqual(info["CFBundleIdentifier"], "com.lakeba.lakebaos-starter")
        self.assertIn("AI model servers", info["NSLocalNetworkUsageDescription"])
        if shutil.which("codesign"):
            check = subprocess.run(["codesign", "--verify", str(app)], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, "re-signed after the change: " + check.stderr)

    def test_installer_names_the_app_it_makes(self):
        text = INSTALL.read_text()
        self.assertLess(text.index('osacompile -o "$APP"'), text.index('name_app "$APP"'))


if __name__ == "__main__":
    unittest.main()
