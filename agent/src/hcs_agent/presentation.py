"""Small, local presentation rules; raw provider events remain in the trace."""

import re


def action_narration(tools: list[str]) -> str:
    """Narrate action types without reading tool arguments, secrets or internal code."""
    phrases = {
        "click_desktop": "Selecting an on-screen control…",
        "click_web": "Selecting an on-screen control…",
        "write_desktop": "Entering text…",
        "write_at_desktop": "Filling in a field…",
        "write_web": "Filling in a field…",
        "press_key_desktop": "Using a keyboard shortcut…",
        "press_keys_desktop": "Using a keyboard shortcut…",
        "scroll_desktop": "Scrolling the page…",
        "scroll_web": "Scrolling the page…",
        "wait_desktop": "Waiting for the page…",
        "wait_web": "Waiting for the page…",
        "screenshot_desktop": "Reading the screen…",
        "navigate_web": "Opening the page…",
        "answer": "Preparing the response…",
    }
    # A compound tool request is still one operation, not a script to read aloud.
    labels = list(dict.fromkeys(phrases.get(name, "Working on the current step…")
                               for name in tools if isinstance(name, str)))
    return " ".join(labels[:2]) or "Working on the current step…"


def paginate_text(text: str, fits) -> list[str]:
    """Split by measured space, preferably at whitespace, without dropping characters.

    `fits` measures a string with the actual drawing font and available dimensions.
    Long URLs also progress one character at a time if no word boundary fits.
    """
    pages = []
    while text:
        if fits(text):
            pages.append(text)
            break
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(text[:mid]):
                lo = mid
            else:
                hi = mid - 1
        end = lo
        sentence = [m.end() for m in re.finditer(r'[.!?]\s+', text[:end])]
        boundary = max((i + 1 for i, c in enumerate(text[:end]) if c.isspace()), default=0)
        if sentence and sentence[-1] >= end / 2:
            end = sentence[-1]
        elif boundary and text[:boundary].strip():
            end = boundary
        pages.append(text[:end])
        text = text[end:]
    return pages or [""]


def reading_seconds(text: str) -> float:
    """Give complete pages time to be read, without delaying generation or input."""
    return max(5.0, min(18.0, len(text.split()) / 3.0 + 1.5))
