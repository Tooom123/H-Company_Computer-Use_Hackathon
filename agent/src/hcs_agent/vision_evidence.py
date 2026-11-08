"""Opt-in, local evidence of the exact JPEG payload used by the Models API.

No full-desktop reference or webcam image is retained. The launcher supplies a
private directory and a session resolver; ordinary runs leave RECORDER unset.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import uuid

RECORDER = None
GEOMETRY = ContextVar('vision_geometry', default=None)


@contextmanager
def geometry(**value):
    token = GEOMETRY.set(value)
    try:
        yield
    finally:
        GEOMETRY.reset(token)


class Recorder:
    def __init__(self, root: Path, session=lambda: {}):
        self.root = root
        self.session = session
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def begin(self, image: str, model: str):
        from PIL import Image
        raw = base64.b64decode(image, validate=True)
        with Image.open(io.BytesIO(raw)) as picture:
            width, height = picture.size
        identifier = uuid.uuid4().hex
        record = dict(self.session() or {})
        record.update(GEOMETRY.get() or {'kind': 'full_screen', 'purpose': 'visual_check'})
        record.update(id=identifier, model=model, created_at=datetime.now(timezone.utc).isoformat(),
                      image_width=width, image_height=height, bytes=len(raw),
                      sha256=hashlib.sha256(raw).hexdigest(), status='prepared', attempts=0,
                      simulated=False, latency_ms=None, usage=None)
        with (self.root / (identifier + '.jpg')).open('xb') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(raw)
        self.write(record)
        return record

    def write(self, record):
        path = self.root / (record['id'] + '.json')
        pending = path.with_suffix('.pending')
        with pending.open('w') as stream:
            os.chmod(stream.name, 0o600)
            json.dump(record, stream)
        pending.replace(path)


def begin(image, model):
    if RECORDER is None:
        return None
    try:
        return RECORDER.begin(image, model)
    except (OSError, ValueError):
        return None  # observability must never interrupt help


def update(record, **changes):
    if record is not None and RECORDER is not None:
        record.update(changes)
        try:
            RECORDER.write(record)
        except OSError:
            pass
