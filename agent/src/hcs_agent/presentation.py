"""Small, local presentation rules; raw provider events remain in the trace."""

import re

CHECKING_RESULT = "Let me check that for you."
WORKING_ACKNOWLEDGEMENT = "Give me a moment, I'll check that."
VERIFIED_RESULT = "I've checked this on screen."
UNVERIFIED_RESULT = "I couldn't confirm the result yet."
STOPPED_RESULT = "I've stopped the task."


def action_narration(tools: list[str]) -> str:
    """Short operational status only; never substitute this for the agent's explanation."""
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


def clean_narration(value) -> str:
    """Keep public prose; reject raw tool/code fallbacks and status-only messages.

    Callers must supply the provider's public content/answer, never reasoning or
    tool arguments. This is a presentation filter, not a general privacy filter.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or text.startswith(("{", "[", "```")):
        return ""
    if re.search(r"\b\w+_(?:desktop|web)\s*\(|\b(?:print|exec|eval|subprocess\.\w+)\s*\(|"
                 r"\b(?:tool_name|tool_reqs|reasoning_content)\s*['\"]?\s*:|```", text):
        return ""
    # Formatting is not useful in the handwritten notes or when read aloud.
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text).replace("**", "")
    text = re.sub(r"(?im)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"(?i)^(?:done|task completed)\s*:\s*", "", text).strip()
    status = text.casefold().rstrip(" .…!")
    if status in {"preparing the response", "reading the screen", "selecting an on-screen control",
                  "entering text", "filling in a field", "using a keyboard shortcut", "scrolling the page",
                  "waiting for the page", "opening the page", "working on the current step", "agent decided",
                  "done", "task completed"}:
        return ""
    return text


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
