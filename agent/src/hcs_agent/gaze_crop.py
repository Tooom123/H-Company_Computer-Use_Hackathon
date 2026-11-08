"""Gaze-assisted screenshots: send Holo the part of the screen the user looks at (opt-in, off by default).

When the user turns Vision on in the desktop app, the gaze points of the webcam tracker (Édouard's Vision Lab)
reach the agent through the control point (`POST /gaze`). When the agent then asks Holo to locate a control,
it sends a crop instead of the whole screen, chosen by the method measured in bench/README.md
("Gaze × clickable controls × intent"):

    p(element) ∝ gaze(element) × intent(element)     over the clickable elements on screen
    gaze(e)   = exp(−d²/2σ²) + 0.02                   d: gaze point → element box, σ: calibration error
    intent(e) = word match(description, label) + 0.15
    crop      = box of the elements holding 80 % of p, + 40 pt, at least 768×480 pt (scaled to the screen)

Clickable elements come from the macOS accessibility tree (a11y.py) when it is available; otherwise the crop is a
box around the gaze alone (also measured: as accurate, a little less robust when the user looks elsewhere).
Holo may answer "not here": the caller then falls back to the full screen. No fresh gaze = full screen.

Benchmark (holo4-35b-a3b, user-style requests, realistic mix): full screen 75 %, gaze × controls × intent 81.8 %
for +6 % cost; gaze alone 83.7 %. Simulated gaze, see bench/README.md for the limits.
"""

from __future__ import annotations

import math
import os
import re
import statistics
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass

MIN_W, MIN_H = 768, 480  # benchmark screen 1440x900; scaled to the real screen width
REF_W = 1440
MARGIN, MASS = 40, 0.8
GAZE_FLOOR, INTENT_FLOOR = 0.02, 0.15
FRESH_S = 1.2  # a gaze older than this is not where the user looks now
DEFAULT_ERROR_PX = 120.0

STOP = set("""a an the to of in on at for my me i it this that is be can could you please want need would like and or
with from page site your some help show open click go get do make le la les un une des de du au aux et ou en sur pour
mon ma mes je j moi tu te vous peux pouvez peut veux voudrais besoin aide aider ce cette cet ces qui que quoi est sont
faire fais montre montrer ouvrir ouvre cliquer clique aller va dans par avec lien bouton link button""".split())
SYNONYMS = [
    "delete remove supprimer supprime retirer effacer trash corbeille revoke revoquer erase",
    "new create creer cree nouveau nouvelle add ajouter ajoute plus",
    "search rechercher recherche chercher cherche find trouver trouve look",
    "login log sign signin connexion connecter connecte account compte",
    "menu navigation nav", "home accueil homepage principale", "save enregistrer sauvegarder sauvegarde",
    "more voir see plus suite details", "next suivant suivante", "previous precedent back retour",
    "settings parametres reglages preferences configuration config", "download telecharger telechargement",
    "comment comments commentaire commentaires discussion", "discard annuler cancel abandonner",
    "confirm valider confirmer validate", "share partager", "filter filters filtrer filtre",
    "group grouper regrouper regroupement", "list liste", "note notes", "message messages send envoyer",
    "activity activities activite activites schedule planifier", "user users utilisateur utilisateurs people",
    "key keys cle cles token api", "credit credits credit redeem", "agent agents",
]
_SYN: dict[str, set[str]] = {}
for _line in SYNONYMS:
    _words = _line.split()
    for _w in _words:
        _SYN.setdefault(_w[:5], set()).update(x[:5] for x in _words)


def _tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 2 and w not in STOP]


def intent_score(request: str, label: str) -> float:
    """Share of the label's words the request mentions (prefix-stemmed, FR/EN action synonyms), 0..1."""
    lab = [w[:5] for w in _tokens(label)]
    if not lab:
        return 0.0
    req: set[str] = set()
    for w in _tokens(request):
        req.add(w[:5])
        req |= _SYN.get(w[:5], set())
    return sum(1 for w in lab if w in req) / len(lab)


@dataclass
class Element:
    label: str
    box: tuple[float, float, float, float]  # x, y, w, h in screen points, top-left origin


def _dist(x: float, y: float, box) -> float:
    bx, by, bw, bh = box
    return math.hypot(max(bx - x, 0, x - (bx + bw)), max(by - y, 0, y - (by + bh)))


def _fit(x0, y0, x1, y1, sw, sh) -> tuple[int, int, int, int]:
    k = sw / REF_W  # sizes were measured on a 1440-pt-wide screen
    m = MARGIN * k
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    w, h = min(max(x1 - x0, MIN_W * k), sw), min(max(y1 - y0, MIN_H * k), sh)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x = min(max(0, cx - w / 2), sw - w)
    y = min(max(0, cy - h / 2), sh - h)
    return int(x), int(y), int(w), int(h)


def choose_crop(gaze: tuple[float, float], sigma: float, screen: tuple[float, float],
                elements: list[Element] | None = None, request: str = "") -> tuple[tuple[int, int, int, int], str]:
    """Crop (x, y, w, h) in screen points, and the strategy used: "gci" (gaze × controls × intent) when elements are
    known, "g" (box around the gaze) otherwise."""
    sw, sh = screen
    gx, gy = gaze
    if not elements:
        half = 1.3 * sigma
        return _fit(gx - half, gy - half, gx + half, gy + half, sw, sh), "g"
    probs = []
    for e in elements:
        d = _dist(gx, gy, e.box)
        probs.append((math.exp(-(d * d) / (2 * sigma * sigma)) + GAZE_FLOOR) * (intent_score(request, e.label) + INTENT_FLOOR))
    total = sum(probs) or 1.0
    acc, box = 0.0, None
    for i in sorted(range(len(elements)), key=lambda k: -probs[k]):
        x, y, w, h = elements[i].box
        b = (x, y, x + w, y + h)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        acc += probs[i] / total
        if acc >= MASS:
            break
    return _fit(*box, sw, sh), "gci"


class GazeState:
    """What the agent knows about the user's gaze. Thread-safe; fed by the control point."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.enabled = os.environ.get("HCS_VISION", "0").lower() in {"1", "true", "yes", "on"}
        self.error_px = DEFAULT_ERROR_PX  # median calibration error (screen points), from the Vision Lab
        self._samples: deque = deque(maxlen=90)  # (t, x, y)
        self.stats = {"crops": 0, "fallbacks": 0, "full_no_gaze": 0, "last_strategy": None}

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            self.enabled = bool(on)
            if not on:
                self._samples.clear()

    def push(self, x: float, y: float, error_px: float | None = None, t: float | None = None) -> None:
        with self._lock:
            if not self.enabled:
                return  # off: gaze is not even kept
            self._samples.append((t or time.time(), float(x), float(y)))
            if error_px and 10 <= error_px <= 600:
                self.error_px = float(error_px)

    def point(self, now: float | None = None) -> tuple[float, float] | None:
        """Where the user looks now: median of the last 0.4 s of samples, if fresh; else None."""
        now = now or time.time()
        with self._lock:
            if not self.enabled:
                return None
            recent = [(x, y) for t, x, y in self._samples if now - t <= 0.4]
            if not recent and self._samples and now - self._samples[-1][0] <= FRESH_S:
                recent = [self._samples[-1][1:]]
        if not recent:
            return None
        return statistics.median(x for x, _ in recent), statistics.median(y for _, y in recent)

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            last = self._samples[-1][0] if self._samples else None
            return {"enabled": self.enabled, "error_px": round(self.error_px),
                    "gaze_age_s": round(now - last, 1) if last else None,
                    "live": bool(last and now - last <= FRESH_S), **self.stats}


STATE = GazeState()
