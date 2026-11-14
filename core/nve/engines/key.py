"""key socket: green screen -> transparent person video (WebM VP9 + alpha), aligned to the cut.

keyfill (default, from the old studio's tools/key_fill.py + fill_holes.py):
    alpha = green-dominance key x dilated AI matte (garbage mask for set edges that are not green),
    dark-ringed holes filled (a phone mirroring the screen), soft key + guided filter in the edge band
    (fine hair), colour decontamination, despill, and alpha = max(key, eroded AI-matte core) to close
    pinholes where dark clothes reflect the green.
    Needs opencv + the HyperFrames CLI (`remove-background`, local AI model).
chromakey (fallback): ffmpeg chromakey + despill. Works anywhere; harder edges, may leave holes.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from nve.engines import Ctx, Engine, EngineFailed
from nve.env import HYPERFRAMES_VERSION
from nve.util import run

VP9_ALPHA = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "18", "-b:v", "0", "-deadline", "good",
             "-cpu-used", "4", "-row-mt", "1", "-auto-alt-ref", "0"]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _guided(cv2, I, p, r=6, eps=2e-4):
    k = (2 * r + 1, 2 * r + 1)
    mI, mp = cv2.boxFilter(I, -1, k), cv2.boxFilter(p, -1, k)
    cov = cv2.boxFilter(I * p, -1, k) - mI * mp
    var = cv2.boxFilter(I * I, -1, k) - mI * mI
    A = cov / (var + eps)
    B = mp - A * mI
    return cv2.boxFilter(A, -1, k) * I + cv2.boxFilter(B, -1, k)


def key_frame(f, matte, screen, cv2, np, scale: float = 1.0):
    """f: HxWx3 uint8 RGB, matte: HxW uint8 (AI alpha). Returns HxWx4 uint8 RGBA."""
    H, W = matte.shape
    ks = lambda n: max(3, int(n * scale) | 1)  # noqa: E731  kernel sizes scale with resolution
    ell = lambda n: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks(n), ks(n)))  # noqa: E731
    f = f.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx = np.maximum(r, b)
    a = np.clip(255 - (g - mx - 3) * 25, 0, 255).astype(np.uint8)
    gm = (matte > 60).astype(np.uint8) * 255
    gm = cv2.resize(cv2.dilate(cv2.resize(gm, (W // 2, H // 2)), ell(23)), (W, H))
    gm = cv2.GaussianBlur(gm, (0, 0), 4 * scale)
    a = ((a.astype(np.uint16) * gm) // 255).astype(np.uint8)
    solid = (a > 128).astype(np.uint8)
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None:
        lum = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)
        s2 = scale * scale
        for i, c in enumerate(cnts):
            if hier[0][i][3] < 0:
                if cv2.contourArea(c) < 4000 * s2:
                    cv2.drawContours(a, [c], -1, 0, -1)
                continue
            area = cv2.contourArea(c)
            if area < 30 * s2 or area > 90000 * s2:
                continue
            x, y, w, h = cv2.boundingRect(c)
            pad = int(20 * scale) + 1
            x0, y0, x1, y1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
            hole = np.zeros((y1 - y0, x1 - x0), np.uint8)
            cv2.drawContours(hole, [c - [x0, y0]], -1, 1, -1)
            ring = (cv2.dilate(hole, ell(19)) - hole) & solid[y0:y1, x0:x1]
            if ring.sum() and lum[y0:y1, x0:x1][ring > 0].mean() < 75:
                a[y0:y1, x0:x1][cv2.dilate(hole, ell(5)) > 0] = 255
    solid2 = (a > 128).astype(np.uint8)
    band = cv2.dilate(solid2, ell(17)) & (1 - cv2.erode(solid2, ell(9)))
    soft = np.clip(255 - (g - mx - 6) * 12, 0, 255).astype(np.uint16) * gm // 255
    a = np.where(band > 0, np.maximum(a, soft.astype(np.uint8)), a)
    I = ((0.299 * r + 0.587 * g + 0.114 * b) / 255).astype(np.float32)
    q = np.clip(_guided(cv2, I, a.astype(np.float32) / 255, r=max(2, int(6 * scale))) * 255, 0, 255).astype(np.uint8)
    a = np.where(band > 0, q, a)
    al = a.astype(np.float32)[..., None] / 255
    Fg = np.clip((f.astype(np.float32) - (1 - al) * np.array(screen, np.float32)) / np.maximum(al, 0.2), 0, 255)
    f = np.where((band > 0)[..., None], Fg, f.astype(np.float32)).astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    g = np.minimum(g, np.maximum(r, b))
    # pinholes in dark clothes: the AI matte is solid inside the body
    core = cv2.erode((matte > 200).astype(np.uint8) * 255, ell(25))
    a = np.maximum(a, cv2.GaussianBlur(core, (ks(9), ks(9)), 0))
    return np.dstack([r, g, b, a]).astype(np.uint8)


class KeyFill(Engine):
    id, capability = "keyfill", "key"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        if not ctx.env.get("opencv"):
            return False, "opencv missing"
        if not ctx.env.get("node"):
            return False, "node >= 22 missing (needed for the AI matte)"
        return True, ""

    def run(self, job: dict, ctx: Ctx) -> dict:
        import cv2
        import numpy as np
        src, out = Path(job["src"]), Path(job["out"])
        W, H, fps = job["width"], job["height"], job["fps"]
        matte = out.with_name(out.stem + "_matte.webm")
        if not matte.exists() or matte.stat().st_mtime < src.stat().st_mtime:
            from nve.env import npx
            r = npx(ctx.env["node"], ["remove-background", str(src), "-o", str(matte), "--quality", "balanced"], timeout=7200)
            if r.returncode != 0 or not matte.exists():
                raise EngineFailed("AI matte failed: " + (r.stderr or r.stdout or "")[-300:])
        screen = _hex_rgb(job.get("screen") or "#1D754E")
        scale = W / 1080
        rd = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-vf",
                               "scale=flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp,format=rgb24",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        ma = subprocess.Popen(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(matte), "-vf",
                               f"alphaextract,scale={W}:{H},format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        wr = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                               "-r", str(fps), "-i", "-", *VP9_ALPHA, str(out)], stdin=subprocess.PIPE)
        n = 0
        while True:
            buf = rd.stdout.read(W * H * 3)
            mb = ma.stdout.read(W * H)
            if len(buf) < W * H * 3 or len(mb) < W * H:
                break
            fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            wr.stdin.write(key_frame(fr, np.frombuffer(mb, np.uint8).reshape(H, W), screen, cv2, np, scale).tobytes())
            n += 1
        wr.stdin.close()
        wr.wait()
        rd.wait()
        ma.wait()
        if n == 0 or wr.returncode != 0:
            raise EngineFailed("keyfill produced no frames")
        return {"out": str(out), "frames": n}


def garbage_rows(frame, np) -> int:
    """Rows above the green screen (ceiling, wall, light stands): the first row from the top where
    the outer columns are mostly green. Everything above it is cut away."""
    f = frame.astype(np.int16)
    H, W = f.shape[:2]
    edge = np.concatenate([f[:, : W // 7], f[:, -W // 7:]], axis=1)
    r, g, b = edge[..., 0], edge[..., 1], edge[..., 2]
    green = ((g > r + 20) & (g > b + 20)).mean(axis=1)
    rows = np.nonzero(green > 0.5)[0]
    return int(rows[0]) if len(rows) else 0


class GreenKey(Engine):
    """Fallback without the AI matte: green-dominance key (numpy only) + despill, plus a simple
    garbage mask that removes whatever sits above the screen. Hair edges are harder than keyfill."""
    id, capability = "greenkey", "key"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        try:
            import numpy  # noqa: F401
            return True, ""
        except ImportError:
            return False, "numpy missing"

    def run(self, job: dict, ctx: Ctx) -> dict:
        import numpy as np
        W, H, fps = job["width"], job["height"], job["fps"]
        rd = subprocess.Popen(["ffmpeg", "-v", "error", "-i", job["src"], "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              stdout=subprocess.PIPE)
        wr = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                               "-r", str(fps), "-i", "-", *VP9_ALPHA, job["out"]], stdin=subprocess.PIPE)
        n, top = 0, None
        while True:
            buf = rd.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            if top is None:
                top = garbage_rows(fr, np)
            f = fr.astype(np.int16)
            r, g, b = f[..., 0], f[..., 1], f[..., 2]
            mx = np.maximum(r, b)
            a = np.clip(255 - (g - mx - 4) * 18, 0, 255).astype(np.uint8)
            a[:top] = 0
            g = np.minimum(g, mx)
            wr.stdin.write(np.dstack([r, g, b, a]).astype(np.uint8).tobytes())
            n += 1
        wr.stdin.close()
        wr.wait()
        rd.wait()
        if n == 0:
            raise EngineFailed("greenkey produced no frames")
        ctx.notes.append("key: used the simple green key (no AI matte): hair edges are harder and green-reflecting "
                         "dark clothes may show small holes")
        return {"out": job["out"], "frames": n}


ENGINES = [KeyFill, GreenKey]
