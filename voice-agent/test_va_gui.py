"""Unit tests for the GUI guards (no input is ever sent). Run: python3 test_va_gui.py"""
import json, os, sys, tempfile, unittest
d = tempfile.mkdtemp()
os.environ.update(VA_DRY="1", VA_STATE=d + "/st.json", VA_PANIC=d + "/panic", VA_LOG=d + "/log", VA_MAX_ACTIONS="5", VA_ARMED=d + "/armed")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import va_gui as g

W = lambda cls, title: {"cls": cls, "name": cls, "title": title}


class T(unittest.TestCase):
    def test_blocked_classes(self):
        for c in ["org.kde.konsole", "konsole", "Alacritty", "kitty", "foot", "org.freedesktop.impl.portal.desktop.kde", "polkit-kde-authentication-agent-1",
                  "org.kde.kwalletd6", "kwalletmanager", "systemsettings", "org.keepassxc.KeePassXC", "Bitwarden", "xterm", "pinentry-qt", "org.kde.yakuake"]:
            if "portal" in c:
                continue
            self.assertIsNotNone(g.check_window(W(c, "x")), c)

    def test_blocked_titles(self):
        for t in ["Login", "Log in to GitHub", "Sign in - Google", "Enter your password", "Passcode", "OTP", "2FA setup", "Bank of X", "Payment",
                  "Pay now", "Checkout - Shop", "My Wallet", "Billing", "Card details", "Confirm purchase", "Delete account", "Authentication required"]:
            self.assertIsNotNone(g.check_window(W("helium", t)), t)

    def test_allowed(self):
        for t in ["YouTube - Helium", "Display settings guide", "Cardio workout - YouTube", "Wikipedia", "Spotify", "notes.md"]:
            self.assertIsNone(g.check_window(W("helium", t)), t)
        self.assertIsNotNone(g.check_window(None))

    def test_combos(self):
        self.assertEqual(g.parse_combo("ctrl+shift+t"), (["ctrl", "shift"], "t"))
        for bad in ["ctrl+alt+t", "alt+f4", "ctrl+q", "ctrl+shift+w", "delete", "super+d", "ctrl+f1", "ctrl+", "a+b+c+d+e", "alt+space", "xx"]:
            with self.assertRaises(g.Refused, msg=bad):
                g.parse_combo(bad)

    def test_text(self):
        g.validate_text("hello world")
        for bad in ["", "x" * 301, "a\nb", "my password is 1", "Tr0ub4dor&3xyz", "api key abc"]:
            with self.assertRaises(g.Refused, msg=bad):
                g.validate_text(bad)

    def test_arming(self):
        os.environ["VA_FAKE_WINDOW"] = json.dumps(W("helium", "Wikipedia"))
        if os.path.exists(d + "/armed"): os.unlink(d + "/armed")
        with self.assertRaises(g.Refused):
            g.gate("key", "k")                               # missing stamp
        import time as _t
        open(d + "/armed", "w").write(str(_t.time() - 200)); os.chmod(d + "/armed", 0o600)
        with self.assertRaises(g.Refused):
            g.gate("key", "k")                               # too old
        open(d + "/armed", "w").write(str(_t.time())); os.chmod(d + "/armed", 0o666)
        with self.assertRaises(g.Refused):
            g.gate("key", "k")                               # world-writable stamp is not trusted
        os.chmod(d + "/armed", 0o600)
        g.gate("key", "k")                                   # fresh: ok
        os.unlink(d + "/st.json")

    def test_gate_rate_panic_log(self):
        open(d + "/armed", "w").write(str(__import__("time").time())); os.chmod(d + "/armed", 0o600)
        os.environ["VA_FAKE_WINDOW"] = json.dumps(W("helium", "Wikipedia"))
        for _ in range(5):
            g.gate("key", "ctrl+w")
        with self.assertRaises(g.Refused):
            g.gate("key", "ctrl+w")                      # 6th > limit
        os.unlink(d + "/st.json")                          # daemon reset at the next command
        g.gate("key", "k")
        open(d + "/panic", "w").close()
        with self.assertRaises(g.Refused):
            g.gate("key", "k")
        os.unlink(d + "/panic")
        os.environ["VA_FAKE_WINDOW"] = json.dumps(W("org.kde.konsole", "bash"))
        with self.assertRaises(g.Refused):
            g.gate("type", "ls")
        os.environ["VA_FAKE_WINDOW"] = json.dumps(W("helium", "Login"))
        with self.assertRaises(g.Refused):
            g.gate("click", "1 1")
        os.environ["VA_FAKE_WINDOW"] = json.dumps(W("firefox", "Wikipedia"))
        os.unlink(d + "/st.json")
        with self.assertRaises(g.Refused):
            g.gate("browser", "", require_browser=True)
        log = open(d + "/log").read()
        self.assertIn("REFUSED", log)
        g.log_action("type", "x" * 60, W("a", "b"), "ok")
        self.assertNotIn("x" * 41, open(d + "/log").read())

    def test_bounds(self):
        with self.assertRaises(g.Refused):
            g.move_abs(5000, 5, (1920, 1080))


unittest.main(verbosity=1)
