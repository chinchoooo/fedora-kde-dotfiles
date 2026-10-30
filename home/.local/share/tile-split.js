var area = workspace.clientArea(KWin.MaximizeArea, workspace.activeScreen, workspace.currentDesktop);
var half = Math.floor(area.width / 2);
workspace.windowList().forEach(function (w) {
  var c = (w.resourceClass || "").toString().toLowerCase();
  print("TILE " + c + " | " + w.caption);
  var left = c.indexOf("konsole") >= 0;
  var right = c.indexOf("helium") >= 0 || (c.indexOf("chromium") >= 0);
  if (!left && !right) return;
  w.fullScreen = false;
  w.setMaximize(false, false);
  w.frameGeometry = { x: area.x + (left ? 0 : half), y: area.y, width: half, height: area.height };
});
