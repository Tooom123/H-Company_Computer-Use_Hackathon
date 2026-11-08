"""Background webcam gaze tracker for the desktop app (Tom): always on, whatever app is in front.

A browser tab or an Electron page stops tracking as soon as it is hidden (and WebGazer crashes Electron 45 on
Linux), so the eyes are read here, in a plain background process:

  camera (OpenCV) -> MediaPipe Face Landmarker (iris + eye corners + head pose) -> features
  calibration: the desktop app shows 9 dots; at each click it asks us to record the features (≥ 8 face frames),
               then we fit a ridge regression features -> screen point (same idea as WebGazer's ridge)
  validation:  4 other dots, just looked at: median distance = the accuracy sent with every gaze point
  tracking:    each frame -> screen point, smoothed (median of the last 5) -> GET /gaze

Nothing leaves this computer: the camera check preview is served locally, never saved or sent to Holo.
Once calibrated, only screen points are forwarded to the agent.

    python gaze_tracker.py [--port 8769] [--camera 0]
    GET  /status                 state (starting|ready|no_camera|calibrating|tracking), fps, face, error_px
    GET  /camera                 local camera preview and face status, for the pre-calibration check
    POST /calibrate/start        forget the previous calibration
    POST /calibrate/point {x,y}  record the features while the user looks at (x, y) (screen points)
    POST /calibrate/fit          fit the model on the recorded points
    POST /validate/point {x,y}   predictions while the user looks at (x, y): their median error
    GET  /gaze                   latest smoothed gaze {x, y, t, error_px} or {} when no face
    POST /quit
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
             "face_landmarker.task")
MODEL_PATH = Path(os.environ.get("HCS_FACE_MODEL", Path.home() / ".cache" / "hcs-companion" / "face_landmarker.task"))

# Face Landmarker (478 points): iris centres and the eye corners / lids around them
R_IRIS, L_IRIS = 468, 473
R_OUT, R_IN, R_UP, R_DOWN = 33, 133, 159, 145
L_IN, L_OUT, L_UP, L_DOWN = 362, 263, 386, 374
NOSE, CHIN, FOREHEAD = 1, 152, 10


def features(lm, matrix=None) -> np.ndarray:
    """Eye-in-head position (iris relative to each eye's corners and lids) + head position and pose."""
    p = lambda i: np.array([lm[i].x, lm[i].y])  # noqa: E731

    def eye(iris, a, b, up, down):
        c = (p(a) + p(b)) / 2
        w = np.linalg.norm(p(b) - p(a)) or 1e-6
        h = np.linalg.norm(p(down) - p(up)) or 1e-6
        d = p(iris) - c
        return [d[0] / w, d[1] / w, h / w]

    nose = p(NOSE)
    face_h = np.linalg.norm(p(CHIN) - p(FOREHEAD)) or 1e-6
    f = eye(R_IRIS, R_OUT, R_IN, R_UP, R_DOWN) + eye(L_IRIS, L_IN, L_OUT, L_UP, L_DOWN)
    f += [nose[0], nose[1], face_h]
    if matrix is not None:  # head rotation: yaw / pitch from the facial transformation matrix
        m = np.asarray(matrix).reshape(4, 4)
        f += [m[0, 2], m[1, 2]]
    else:
        f += [0.0, 0.0]
    return np.array(f, dtype=np.float64)


class Ridge:
    """Ridge regression on standardised features with second-order terms, one model per screen axis."""

    def __init__(self, lam: float = 1e-2) -> None:
        self.lam = lam
        self.mu = self.sd = self.w = None

    @staticmethod
    def _expand(z: np.ndarray) -> np.ndarray:
        eyes = z[:, :6]
        quad = np.einsum("ni,nj->nij", eyes, eyes)[:, np.triu_indices(6)[0], np.triu_indices(6)[1]]
        return np.hstack([np.ones((len(z), 1)), z, quad])

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        self.mu, self.sd = x.mean(0), x.std(0) + 1e-6
        a = self._expand((x - self.mu) / self.sd)
        reg = self.lam * np.eye(a.shape[1])
        reg[0, 0] = 0
        self.w = np.linalg.solve(a.T @ a + reg, a.T @ y)

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self._expand((np.atleast_2d(x) - self.mu) / self.sd) @ self.w


class Tracker:
    def __init__(self, camera: int) -> None:
        self.camera = camera
        self.state = "starting"
        self.message = ""
        self.lock = threading.Lock()
        self.last_feat: tuple[float, np.ndarray] | None = None
        self.recent: deque = deque(maxlen=90)  # (monotonic time, features) of the last ~3 s, for instant calibration
        self.frames = deque(maxlen=60)  # frame times (fps)
        self.calib_x: list[np.ndarray] = []
        self.calib_y: list[tuple[float, float]] = []
        self.model: Ridge | None = None
        self.error_px: float | None = None
        self.preds: deque = deque(maxlen=5)
        self.gaze: dict = {}
        self.stop = threading.Event()
        self.preview: str | None = None
        self.preview_at = 0.0

    # ------------------------------------------------------------------ camera loop
    def run(self) -> None:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

        if not MODEL_PATH.exists():
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.message = "downloading the face model (3.6 MB, once)"
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        opts = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
                                     running_mode=RunningMode.VIDEO, num_faces=1,
                                     output_facial_transformation_matrixes=True)
        landmarker = FaceLandmarker.create_from_options(opts)
        cap = cv2.VideoCapture(self.camera)
        if not cap.isOpened():
            self.state, self.message = "no_camera", "The camera is busy or missing: close any page that uses it."
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.state, self.message = "ready", ""
        t0 = time.monotonic()
        while not self.stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            if now - self.preview_at > 0.25:
                # Small, mirrored local preview for the camera check. Never stored or sent to the agent.
                ok_jpeg, jpeg = cv2.imencode(".jpg", cv2.flip(cv2.resize(frame, (320, 240)), 1),
                                           [cv2.IMWRITE_JPEG_QUALITY, 65])
                if ok_jpeg:
                    with self.lock:
                        self.preview = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
                        self.preview_at = now
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = landmarker.detect_for_video(img, int((now - t0) * 1000))
            self.frames.append(now)
            if not res.face_landmarks:
                with self.lock:
                    self.last_feat = None
                    if now - self.gaze.get("mono", 0) > 0.5:
                        self.gaze = {}
                continue
            mat = res.facial_transformation_matrixes[0] if res.facial_transformation_matrixes else None
            f = features(res.face_landmarks[0], mat)
            with self.lock:
                self.last_feat = (now, f)
                self.recent.append((now, f))
                if self.model is not None and self.state == "tracking":
                    x, y = self.model.predict(f)[0]
                    self.preds.append((x, y))
                    self.gaze = {"x": float(statistics.median(p[0] for p in self.preds)),
                                 "y": float(statistics.median(p[1] for p in self.preds)),
                                 "t": time.time(), "mono": now, "error_px": self.error_px}
        cap.release()

    # ------------------------------------------------------------------ calibration
    def _collect(self, seconds: float, minimum: int) -> list[np.ndarray]:
        out, seen, end = [], None, time.monotonic() + seconds
        while time.monotonic() < end or len(out) < minimum:
            if time.monotonic() > end + 1.5:
                break
            with self.lock:
                lf = self.last_feat
            if lf and lf[0] != seen:
                seen = lf[0]
                out.append(lf[1])
            time.sleep(0.01)
        return out

    def calib_point(self, x: float, y: float) -> dict:
        """The user clicks the dot they are already looking at: use the features of the last 0.5 s before the click
        (instant), and only wait a little if the face was not seen in that window."""
        self.state = "calibrating"
        now = time.monotonic()
        with self.lock:
            feats = [f for t, f in self.recent if now - t <= 0.5]
        if len(feats) < 3:
            feats += self._collect(0.4, 3)
        if len(feats) < 3:
            return {"ok": False, "error": "no face: look at the dot, face the camera"}
        for f in feats:
            self.calib_x.append(f)
            self.calib_y.append((x, y))
        return {"ok": True, "samples": len(self.calib_x)}

    def fit(self) -> dict:
        if len({tuple(p) for p in self.calib_y}) < 6:
            return {"ok": False, "error": "calibrate at least 6 dots"}
        m = Ridge()
        m.fit(np.array(self.calib_x), np.array(self.calib_y, dtype=np.float64))
        with self.lock:
            self.model = m
            self.preds.clear()
            self.state = "tracking"
        return {"ok": True}

    def validate_point(self, x: float, y: float) -> dict:
        if self.model is None:
            return {"ok": False, "error": "not calibrated"}
        feats = self._collect(1.0, 8)
        if not feats:
            return {"ok": False, "error": "no face"}
        d = [float(np.hypot(*(self.model.predict(f)[0] - (x, y)))) for f in feats]
        err = statistics.median(d)
        return {"ok": True, "error_px": err}

    def set_error(self, px: float) -> None:
        self.error_px = round(px)

    def status(self) -> dict:
        fps = 0.0
        if len(self.frames) > 1 and time.monotonic() - self.frames[-1] < 1:
            fps = (len(self.frames) - 1) / max(1e-6, self.frames[-1] - self.frames[0])
        with self.lock:
            face = bool(self.last_feat and time.monotonic() - self.last_feat[0] < 0.5)
        return {"state": self.state, "message": self.message, "fps": round(fps, 1), "face": face,
                "calibrated": self.model is not None, "error_px": self.error_px, "points": len(set(self.calib_y))}


def serve(tr: Tracker, port: int) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _reply(self, code, payload):
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/camera":
                result = tr.status()
                with tr.lock:
                    result["preview"] = tr.preview if time.monotonic() - tr.preview_at < 1 else None
                return self._reply(200, result)
            if self.path == "/status":
                return self._reply(200, tr.status())
            if self.path == "/gaze":
                with tr.lock:
                    g = {k: v for k, v in tr.gaze.items() if k != "mono"}
                return self._reply(200, g)
            self._reply(404, {})

        def do_POST(self):  # noqa: N802
            n = min(int(self.headers.get("Content-Length") or 0), 1000)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._reply(400, {"error": "json"})
            x, y = body.get("x"), body.get("y")
            if self.path == "/calibrate/start":
                with tr.lock:
                    tr.calib_x, tr.calib_y, tr.model, tr.error_px, tr.gaze = [], [], None, None, {}
                tr.state = "calibrating"
                return self._reply(200, {"ok": True})
            if self.path == "/calibrate/point" and isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return self._reply(200, tr.calib_point(float(x), float(y)))
            if self.path == "/calibrate/fit":
                return self._reply(200, tr.fit())
            if self.path == "/validate/point" and isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return self._reply(200, tr.validate_point(float(x), float(y)))
            if self.path == "/accuracy" and isinstance(body.get("px"), (int, float)):
                tr.set_error(float(body["px"]))
                return self._reply(200, {"ok": True})
            if self.path == "/quit":
                tr.stop.set()
                threading.Thread(target=httpd.shutdown, daemon=True).start()
                return self._reply(200, {"ok": True})
            self._reply(400, {"error": "bad request"})

    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8769)
    ap.add_argument("--camera", type=int, default=int(os.environ.get("HCS_CAMERA", "0")))
    a = ap.parse_args()
    tr = Tracker(a.camera)
    httpd = serve(tr, a.port)
    threading.Thread(target=tr.run, daemon=True).start()
    print(f"gaze tracker on http://127.0.0.1:{a.port}", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
