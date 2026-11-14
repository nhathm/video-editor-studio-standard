"""Shot boundary detection for reference analysis and the visual cut strategy.

Adapted from rea-video (Apache-2.0, Copyright 2026 JuneYaooo), rea_video/shots.py; see NOTICE in this folder.
Kept: hard cuts on an adaptive threshold, same-camera jump cuts, flash / strobe rejection, fades through
black or white, short inserts between two clean cuts, cuts that open on a decaying flash. Dropped: dissolve,
wipe and gradual-transition analysis, motion-graphics beats, everything about how footage was made.
Changed: frames come from an ffmpeg pipe and colour histograms are computed with numpy, so no OpenCV is needed;
a fade needs a different picture after it (a white flash over one shot is not a fade); a short dark opening
is the video fading in and joins the first shot.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import numpy as np

from nve.paths import NveError

THUMB_W = 96
# jump cuts (same camera, subject jumps): share of the frame that changes, how far above the frames on both
# sides, frames on each side that must stay quiet, and how little the picture may drift back (see _returns)
JUMP_MIN_CHANGED, JUMP_RATIO, JUMP_QUIET, JUMP_MIN_RETURN = 0.17, 2.5, 2, 0.7
SHORT_SHOT_S = 0.12  # shortest shot kept between two clean hard cuts (4 frames at 30 fps)


@dataclass
class FrameTrack:
    fps: float
    hist_dist: np.ndarray       # Bhattacharyya distance of the HSV histogram to the previous frame (0..1)
    pix_diff: np.ndarray        # mean |diff| of grey thumbs, 0..1
    changed: np.ndarray         # share of thumb pixels that changed noticeably
    luma: np.ndarray            # mean luma 0..255
    thumbs: list[np.ndarray] = field(repr=False, default_factory=list)  # grey thumbs, uint8

    @property
    def n(self) -> int:
        return len(self.luma)


# ── frames ──
def iter_frames(path: str, width: int = THUMB_W, height: int | None = None, start: float = 0.0,
                duration: float | None = None):
    """BGR uint8 frames scaled to `width` (height keeps the aspect, rounded to even), decoded by ffmpeg."""
    if height is None:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0:s=x", path], capture_output=True, text=True)
        try:
            w0, h0 = (int(x) for x in r.stdout.strip().split("x")[:2])
        except ValueError as e:
            raise NveError(f"Cannot read video size of {path}") from e
        height = max(2, int(round(width * h0 / w0 / 2)) * 2)
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-an", "-vf", f"scale={width}:{height}", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
    size = width * height * 3
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(height, width, 3)
    finally:
        p.stdout.close()
        p.wait()


def grey(bgr: np.ndarray) -> np.ndarray:
    b, g, r = bgr[..., 0].astype(np.float32), bgr[..., 1].astype(np.float32), bgr[..., 2].astype(np.float32)
    return 0.114 * b + 0.587 * g + 0.299 * r


def hsv_hist(bgr: np.ndarray) -> np.ndarray:
    """L1-normalised 16x4x4 histogram over OpenCV-style HSV (H 0..180, S and V 0..255)."""
    x = bgr.reshape(-1, 3).astype(np.float32) / 255.0
    b, g, r = x[:, 0], x[:, 1], x[:, 2]
    v = x.max(axis=1)
    mn = x.min(axis=1)
    d = v - mn
    s = np.where(v > 0, d / np.maximum(v, 1e-9), 0.0)
    dd = np.maximum(d, 1e-9)
    h = np.where(v == r, (g - b) / dd, np.where(v == g, 2.0 + (b - r) / dd, 4.0 + (r - g) / dd))
    h = np.where(d > 0, (h * 60.0) % 360.0, 0.0) / 2.0  # 0..180
    hi = np.clip((h / 180.0 * 16).astype(int), 0, 15)
    si = np.clip((s * 4).astype(int), 0, 3)
    vi = np.clip((v * 4).astype(int), 0, 3)
    hist = np.bincount(hi * 16 + si * 4 + vi, minlength=256).astype(np.float32)
    return hist / max(1.0, hist.sum())


def bhattacharyya(h1: np.ndarray, h2: np.ndarray) -> float:
    return float(np.sqrt(max(0.0, 1.0 - float(np.sqrt(h1 * h2).sum()))))


def build_track(path: str, fps: float) -> FrameTrack:
    hist_d, pix_d, chg, luma, thumbs = [], [], [], [], []
    prev_h = prev_g = None
    for bgr in iter_frames(path):
        g = grey(bgr)
        h = hsv_hist(bgr)
        if prev_h is None:
            hist_d.append(0.0)
            pix_d.append(0.0)
            chg.append(0.0)
        else:
            d = np.abs(g - prev_g)
            hist_d.append(bhattacharyya(prev_h, h))
            pix_d.append(float(d.mean() / 255.0))
            thr = max(6.0, 0.35 * float(min(g.std(), prev_g.std())))
            chg.append(float((d > thr).mean()))
        luma.append(float(g.mean()))
        thumbs.append(np.clip(g, 0, 255).astype(np.uint8))
        prev_h, prev_g = h, g
    return FrameTrack(fps=fps if fps > 0 else 30.0, hist_dist=np.array(hist_d), pix_diff=np.array(pix_d),
                      changed=np.array(chg), luma=np.array(luma), thumbs=thumbs)


# ── detection ──
def _local_median(x: np.ndarray, radius: int) -> np.ndarray:
    out = np.empty_like(x)
    n = len(x)
    for i in range(n):
        lo, hi = max(0, i - radius), min(n, i + radius + 1)
        window = np.concatenate([x[lo:i], x[i + 1:hi]]) if hi - lo > 1 else x[lo:hi]
        out[i] = np.median(window) if len(window) else 0.0
    return out


def detect(track: FrameTrack, min_shot_s: float = 0.35, cut_threshold: float = 0.30) -> list[dict]:
    """Shots as [{"index", "start", "end", "duration", "transition_in", "strength", "flash_s"?}] in seconds.
    transition_in: start | cut | jump (same camera) | fade (through black/white) | flash (cut opening on a flash)."""
    n, fps = track.n, track.fps
    if n == 0:
        return []
    score = 0.6 * track.hist_dist + 0.4 * np.clip(track.pix_diff * 4.0, 0, 1)
    score[0] = 0.0
    radius = max(4, int(round(fps * 0.5)))
    base = _local_median(score, radius)
    chg = track.changed
    chg_base = _local_median(chg, radius)
    boundaries: dict[int, tuple[str, float]] = {}

    # 1) hard cuts: a spike well above local activity that changes most of the frame (a title popping in over a
    #    static layout changes only a region -> not a cut); plus jump cuts and swaps between still layouts
    for i in range(1, n):
        s = score[i]
        strong = s > cut_threshold and s > base[i] * 2.5 + 0.06 and chg[i] > 0.25
        relative = chg[i] > 0.45 and chg[i] > chg_base[i] * 3 + 0.2 and s > base[i] * 4 + 0.03
        still_swap = (s > cut_threshold and track.hist_dist[i] > 0.25 and chg[i] > 0.18 and chg_base[i] < 0.01
                      and s > base[i] * 5 + 0.1 and i >= 3 and float(track.pix_diff[i - 3:i].max()) < 1e-3)
        jump = _jump_cut(track, i)
        if strong or relative or still_swap or jump:
            if _brief_flash(track, i) or _back_to_before(track.thumbs, i):
                continue  # a strobe / one- or two-frame flash or glitch: the picture comes back, nothing was cut
            same_take = jump and track.hist_dist[i] < 0.4 and chg[i] < 0.5
            boundaries[i] = ("jump" if same_take else "cut", float(max(s, chg[i])))

    # 2) fades through black / white: luma dips to an extreme, through an (almost) uniform frame, and comes back
    lo_l = min(10.0, float(np.percentile(track.luma, 50)) * 0.35)
    dark = (track.luma < lo_l) | (track.luma > 248)
    i = 0
    while i < n:
        if dark[i]:
            j = i
            while j < n and dark[j]:
                j += 1
            flat = min(float(track.thumbs[k].std()) for k in range(i, j)) < 4.0
            # the picture after must differ from the one before (a white flash over one shot is not a fade)
            new_pic = j < n and float(np.abs(track.thumbs[i - 1].astype(np.float32) - track.thumbs[j].astype(np.float32)).mean()) > 12
            if 0 < i and j < n and (j - i) <= fps * 2.5 and flat and new_pic and not any(abs(j - b) < radius for b in boundaries):
                boundaries[j] = ("fade", 0.5)
            i = j
        else:
            i += 1

    # assemble; boundaries closer than min_shot_s are one event: keep the strongest. A very short shot survives
    # between two clean hard cuts (a 4-frame insert in a fast edit).
    min_len = max(1, int(round(min_shot_s * fps)))
    short_len = max(1, int(round(SHORT_SHOT_S * fps)))
    kept: list[int] = []
    for b in sorted(boundaries):
        prev = kept[-1] if kept else 0
        gap = b - prev
        if gap >= min_len or (gap >= short_len and _clean_cut(boundaries, b) and (not kept or _clean_cut(boundaries, prev))
                              and float(chg[prev + 1:b].max(initial=0.0)) < 0.3):
            kept.append(b)
        elif kept and boundaries[b][1] > boundaries[prev][1] and b - (kept[-2] if len(kept) > 1 else 0) >= short_len:
            kept[-1] = b
    if kept and n - kept[-1] < min_len:
        kept.pop()
    # a short opening that is (almost) black is the video fading in, not a shot of its own
    fade_in = bool(kept) and kept[0] <= int(fps * 0.8) and float(np.median(track.luma[:kept[0]])) < 25
    if fade_in:
        kept.pop(0)
    shots, start, kind, strength = [], 0, "start", 0.0
    for b in kept + [n]:
        sh = {"index": len(shots) + 1, "start": round(start / fps, 3), "end": round(b / fps, 3),
              "duration": round((b - start) / fps, 3), "transition_in": kind, "strength": round(strength, 3)}
        if kind == "cut":
            f = _flash(track.luma, start, b, fps)
            if f:
                sh.update({"transition_in": "flash", "flash_s": round(f, 2)})
        if not shots and fade_in:
            sh["fade_in"] = True
        shots.append(sh)
        if b < n:
            kind, strength = boundaries[b]
        start = b
    return shots


def _clean_cut(boundaries: dict[int, tuple[str, float]], b: int) -> bool:
    kind, strength = boundaries[b]
    return kind in ("cut", "jump") and strength >= 0.35


def _brief_flash(track: FrameTrack, i: int) -> bool:
    """A muzzle flash / strobe: brighter than just before, mostly gone two frames later, and the picture returns."""
    pre = float(track.luma[max(0, i - 3):i].min())
    rise = float(track.luma[i]) - pre
    if rise <= 5.0 or i + 2 >= track.n:
        return False
    return float(track.luma[i + 2]) - pre < 0.5 * rise and _returns(track.thumbs, i) < 0.6


def _back_to_before(thumbs: list[np.ndarray], i: int) -> bool:
    """Frame i looks like the picture two or three frames earlier: the end of a short flash or glitch."""
    if i < 3:
        return False
    cur = thumbs[i].astype(np.float32)
    first = float(np.abs(cur - thumbs[i - 1].astype(np.float32)).mean()) + 1e-6
    return min(float(np.abs(cur - thumbs[j].astype(np.float32)).mean()) for j in (i - 3, i - 2)) < 0.3 * first


def _returns(thumbs: list[np.ndarray], i: int, span: int = 4) -> float:
    """How far the picture stays away after frame i, relative to the jump into it: ~1 for a cut, well below 1
    when a flash or strobe fades back."""
    n = len(thumbs)
    if i < 1 or i + 1 >= n:
        return 1.0
    cur = thumbs[i].astype(np.float32)
    first = float(np.abs(cur - thumbs[i - 1].astype(np.float32)).mean()) + 1e-6
    best = float("inf")
    for j in range(max(0, i - 3), i):
        a = thumbs[j].astype(np.float32)
        jump = float(np.abs(cur - a).mean()) + 1e-6
        if jump < 0.2 * first:
            continue
        later = min(float(np.abs(thumbs[k].astype(np.float32) - a).mean()) for k in range(i + 1, min(n, i + 1 + span)))
        best = min(best, later / jump)
    return best if best != float("inf") else 1.0


def _jump_cut(track: FrameTrack, i: int) -> bool:
    """Same camera and background, the subject jumps in one frame while both sides stay steady."""
    n = track.n
    if i < 4 or i + 4 > n:
        return False
    c, d = track.changed, track.pix_diff
    if c[i] < JUMP_MIN_CHANGED:
        return False
    side_c = max(float(np.median(c[max(0, i - 6):i])), float(np.median(c[i + 1:i + 7])))
    side_d = max(float(np.median(d[max(0, i - 6):i])), float(np.median(d[i + 1:i + 7])))
    if c[i] < JUMP_RATIO * (side_c + 0.02) or d[i] < 2.0 * (side_d + 0.004):
        return False
    near = np.concatenate([c[i - JUMP_QUIET:i], c[i + 1:i + 1 + JUMP_QUIET]])
    if float(near.max()) > 0.5 * float(c[i]):
        return False
    return _returns(track.thumbs, i) >= JUMP_MIN_RETURN


def _flash(luma: np.ndarray, start: int, end: int, fps: float) -> float:
    """A cut opening on a bright flash that decays into the new shot: seconds until it settles, or 0."""
    if start < 1 or end - start < 3:
        return 0.0
    before = float(np.median(luma[max(0, start - 3):start]))
    settle = float(np.median(luma[start + 1:end][-max(1, min(end - start - 1, int(fps))):]))
    jump = float(luma[start]) - max(before, settle)
    if jump < 40:
        return 0.0
    k = start
    while k + 1 < end and luma[k + 1] - settle > 0.2 * jump:
        k += 1
    if k == start or k - start > fps * 1.5:
        return 0.0
    return (k + 1 - start) / fps


def shots_of(path: str, fps: float, min_shot_s: float = 0.35) -> list[dict]:
    return detect(build_track(path, fps), min_shot_s=min_shot_s)


def pace(shots: list[dict], duration: float) -> dict:
    """Edit pace of a list of shots."""
    n = len(shots)
    kinds: dict[str, int] = {}
    for s in shots[1:]:
        kinds[s["transition_in"]] = kinds.get(s["transition_in"], 0) + 1
    lens = [s["duration"] for s in shots] or [0.0]
    return {"shots": n, "cuts_per_min": round(60 * max(0, n - 1) / max(duration, 1e-6), 1),
            "avg_shot_s": round(duration / max(n, 1), 2), "median_shot_s": round(float(np.median(lens)), 2),
            "shortest_s": round(min(lens), 2), "longest_s": round(max(lens), 2), "transitions": kinds}
