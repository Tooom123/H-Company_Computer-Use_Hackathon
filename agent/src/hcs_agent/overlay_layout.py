"""Geometry shared by the native Magnet view and its input exclusion region."""

MAGNET_EXPANDED = (330.0, 80.0)
MAGNET_COMPACT = (176.0, 48.0)


def magnet_size(compact: bool) -> tuple[float, float]:
    return MAGNET_COMPACT if compact else MAGNET_EXPANDED


def magnet_rect(screen_height: float, compact: bool) -> tuple[float, float, float, float]:
    w, h = magnet_size(compact)
    return 18.0, screen_height - 18.0 - h, w, h


def magnet_hit(x: float, y: float, compact: bool) -> str | int | None:
    """Local bottom-left coordinates. Toggling never changes the selected autonomy."""
    w, h = magnet_size(compact)
    if not (0 <= x < w and 0 <= y < h):
        return None
    if compact:
        return "expand"
    if w - 36 <= x < w - 6 and h - 36 <= y < h - 6:
        return "collapse"
    if 12 <= x < w - 12 and 8 <= y <= 36:
        return min(2, int((x - 12) / ((w - 24) / 3)))
    return None


def is_idle_badge(text: str, pulsing: bool) -> bool:
    """Only the persistent shortcut reminder may disappear; active/error/stop statuses stay visible."""
    if pulsing:
        return False
    value = text.strip().lower()
    return value.endswith(": new request") or (value.startswith("hold ") and
           (value.endswith("and speak") or value.endswith("and say what you need")))


def shortcut_label(key: str) -> str:
    symbols = {"cmd": "⌘", "command": "⌘", "ctrl": "⌃", "control": "⌃", "shift": "⇧", "alt": "⌥", "option": "⌥"}
    return "".join(symbols.get(part.lower(), part.upper()) for part in key.split("+"))[:24]
