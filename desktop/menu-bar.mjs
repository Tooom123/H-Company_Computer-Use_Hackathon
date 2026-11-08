// No timers or status polling here: a background tray must not count as an open assistant window.
export function createMenuBar({ Tray, Menu, nativeImage, dialog, iconPath, showWindow, stopTask, startRuntime, quit, coachLabel = "Devin coach" }) {
  const icon = nativeImage.createFromPath(iconPath);
  if (icon.isEmpty()) throw new Error("The H Companion menu-bar icon could not be loaded.");
  icon.setTemplateImage(true); // macOS supplies the correct light/dark menu-bar colour.
  const tray = new Tray(icon);
  tray.setToolTip("H Companion — open, start coach or stop a task");
  let busy = false;
  let message = "H Companion";

  function update() {
    if (tray.isDestroyed()) return;
    const items = [
      { label: message, enabled: false },
      { label: "Open H Companion", click: showWindow },
      { label: "Stop task", enabled: !busy, click: stop },
    ];
    if (startRuntime) items.push({ label: `Start ${coachLabel}`, enabled: !busy, click: start });
    items.push({ type: "separator" }, { label: "Quit H Companion", click: quit });
    tray.setContextMenu(Menu.buildFromTemplate(items));
  }

  async function stop() {
    if (busy) return;
    busy = true;
    message = "Requesting stop…";
    update();
    try {
      const result = await stopTask();
      if (!result.ok) throw new Error(result.offline
        ? "The coach is not responding. Start it again, then retry if a task is still active."
        : "The coach did not accept the stop request. Open H Companion to check the task, then retry.");
      message = result.data?.stopped ? "Stop requested — check Activity" : "No active task to stop";
    } catch (error) {
      message = "Stop was not confirmed";
      if (!tray.isDestroyed()) await dialog.showMessageBox({ type: "warning", title: "H Companion", message,
        detail: error.message, buttons: ["OK"] });
    } finally {
      busy = false;
      update();
    }
  }

  async function start() {
    if (busy || !startRuntime) return;
    busy = true;
    message = `Starting ${coachLabel}…`;
    update();
    try {
      const result = await startRuntime();
      if (!result.ok) throw new Error(result.message || "The coach could not start. Try the launch shortcut again.");
      message = `${coachLabel} ready`;
      if (!tray.isDestroyed()) showWindow();
    } catch (error) {
      message = "Coach could not start";
      if (!tray.isDestroyed()) await dialog.showMessageBox({ type: "warning", title: "H Companion", message,
        detail: error.message, buttons: ["OK"] });
    } finally {
      busy = false;
      update();
    }
  }

  tray.on("double-click", showWindow);
  update();
  return tray;
}
