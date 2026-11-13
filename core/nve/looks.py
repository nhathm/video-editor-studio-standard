"""Colour looks. Each look has a numpy implementation (best, needs opencv for skin retouch) and an
ffmpeg-filter approximation used when numpy/opencv are not available (e.g. a bare sandbox)."""
from __future__ import annotations

from typing import Callable

import numpy as np

LOOKS = {
    "none": {"label": {"vi": "Giữ màu gốc", "en": "Original"}, "ffmpeg": ""},
    "trong-tro": {"label": {"vi": "Trong trẻo", "en": "Clean & bright"},
                  "ffmpeg": "eq=gamma=1.18:contrast=0.97:saturation=0.95:brightness=0.02,colorbalance=bm=0.02:rm=-0.015"},
}


def _trong_tro(x: np.ndarray) -> np.ndarray:
    x = np.clip((0.05 + 0.95 * np.power(np.clip(x, 0, 1), 0.82)) * 1.02, 0, 1)
    g = x.mean(axis=2, keepdims=True)
    x = np.clip(g + (x - g) * 0.95, 0, 1)
    return np.clip(x * np.array([1.03, 1.0, 0.98], np.float32), 0, 1)  # BGR order, identical to the studio's approved look


def _skin(x: np.ndarray) -> np.ndarray:
    import cv2
    h, w = x.shape[:2]
    small = cv2.resize((x * 255).astype(np.uint8), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    m = cv2.inRange(cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb), (40, 135, 85), (255, 180, 135))
    m = cv2.GaussianBlur(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), (17, 17), 0)
    sm = cv2.bilateralFilter(small, 9, 40, 8)
    m = cv2.resize(m, (w, h)).astype(np.float32)[..., None] / 255
    sm = cv2.resize(sm, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    sm = np.power(np.clip((x * 0.3 + sm * 0.7) * np.array([1.01, 1.0, 0.975], np.float32), 0, 1), 0.94)
    return x * (1 - m) + sm * m


NUMPY = {"trong-tro": _trong_tro}


def numpy_pipeline(look: str, skin: bool, opencv: bool) -> Callable[[np.ndarray], np.ndarray] | None:
    """Return f(uint8 BGR frame) -> uint8 frame, or None when ffmpeg should do the look."""
    if look not in NUMPY and not (skin and opencv):
        return None
    if skin and not opencv:
        return None
    fn = NUMPY.get(look)

    def f(frame: np.ndarray) -> np.ndarray:
        x = frame.astype(np.float32) / 255
        if fn:
            x = fn(x)
        if skin:
            x = _skin(x)
        return (np.clip(x, 0, 1) * 255).astype(np.uint8)
    return f


def ffmpeg_filter(look: str) -> str:
    return LOOKS.get(look, LOOKS["none"])["ffmpeg"]
