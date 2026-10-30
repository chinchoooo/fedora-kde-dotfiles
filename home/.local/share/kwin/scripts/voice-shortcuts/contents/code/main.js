function start(unit) {
  callDBus("org.freedesktop.systemd1", "/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager",
           "StartUnit", unit + ".service", "replace");
}
registerShortcut("Dictate on-device", "Dictate on-device (toggle)", "Alt+Space", function () { start("dictate"); });
registerShortcut("Dictate on-device 2", "Dictate on-device (alternate key)", "Ctrl+Alt+Space", function () { start("dictate"); });
registerShortcut("Voice command", "Voice command agent (toggle)", "Meta+Alt+V", function () { start("voice-act"); });
registerShortcut("Split Konsole and Helium", "Split Konsole and Helium", "Meta+Alt+T", function () { start("tile-split"); });
// focus flag: lets spoken replies stay silent while the user is in the terminal
function flag(w) {
  var c = w ? String(w.resourceClass).toLowerCase() : "";
  start(c.indexOf("konsole") >= 0 ? "focus-console" : "focus-away");
}
workspace.windowActivated.connect(flag);
flag(workspace.activeWindow);
