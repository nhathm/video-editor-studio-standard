"""Beat and music analysis of a soundtrack: is there a voice, is there music, its tempo and beat grid, where the
music changes, and whether the edit cuts on the beat.

Adapted from rea-video (Apache-2.0, Copyright 2026 JuneYaooo), rea_video/audio.py; see NOTICE in this folder.
Kept: STFT, harmonic/percussive separation by median filtering, the speech / music-bed windows, tempo by
autocorrelation of the percussive onset curve (75-180 BPM octave), the beat grid (best comb phase snapped to
onset peaks), the no-drums guard, music section changes, cuts-on-beat and cuts-on-onset ratios.
Dropped: pitch / F0, vocal style, held-tone check, musical key, sound-effect typing, TTS and music-source guesses.
Added (nve): `character`: brightness, drums, energy and a mood hint, to pick a track of the same feel.
Changed: returns a compact dict for `nve ref`; the beat list is capped; numpy only; the no-drums floor uses the
97th instead of the 90th percentile of the percussive share, so sparse hits still count.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 22050
N_FFT = 1024
HOP = 256
T_HOP = HOP / SR
PERC_FLOOR = 1e-3                 # percussive share below which there is nothing to count a tempo from
WEAK_PERC, WEAK_BEAT = 0.045, 0.2  # both this low: no drums, no tempo to report
MAX_BEATS = 600


def extract_audio(path: str | Path, sr: int = SR) -> np.ndarray | None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _stft(x: np.ndarray) -> np.ndarray:
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(x[idx] * np.hanning(N_FFT)[None, :], axis=1)).astype(np.float32)


def _median_filter(a: np.ndarray, size: int, axis: int, chunk: int = 600) -> np.ndarray:
    pad = size // 2
    if axis == 0:
        padded = np.pad(a, ((pad, pad), (0, 0)), mode="edge")
        out = np.empty_like(a)
        for s in range(0, a.shape[0], chunk):
            e = min(a.shape[0], s + chunk)
            win = np.lib.stride_tricks.sliding_window_view(padded[s:e + 2 * pad], size, axis=0)
            out[s:e] = np.median(win, axis=-1)
        return out
    return _median_filter(a.T, size, 0, chunk).T


def hpss(S: np.ndarray, size: int = 17) -> tuple[np.ndarray, np.ndarray]:
    H = _median_filter(S, size, axis=0)
    P = _median_filter(S, size, axis=1)
    mh = H ** 2 / (H ** 2 + P ** 2 + 1e-12)
    return S * mh, S * (1 - mh)


def _peaks(env: np.ndarray, min_gap: int, thr: float) -> np.ndarray:
    if len(env) < 3:
        return np.array([], int)
    c = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > thr))[0] + 1
    picked: list[int] = []
    for i in c[np.argsort(-env[c])]:
        if all(abs(i - p) >= min_gap for p in picked):
            picked.append(int(i))
    return np.array(sorted(picked), int)


def _runs(flags: np.ndarray, win_s: float, min_len_s: float = 0.6, merge_gap_s: float = 0.6) -> list[list[float]]:
    segs: list[list[float]] = []
    i, n = 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            a, b = i * win_s, j * win_s
            if segs and a - segs[-1][1] <= merge_gap_s:
                segs[-1][1] = b
            else:
                segs.append([a, b])
            i = j
        else:
            i += 1
    return [[round(a, 2), round(b, 2)] for a, b in segs if b - a >= min_len_s]


def _chroma(S: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    valid = (freqs > 60) & (freqs < 4000)
    pc = (np.round(12 * np.log2(freqs[valid] / 440.0)) + 9) % 12
    C = np.zeros((S.shape[0], 12), np.float32)
    for k in range(12):
        C[:, k] = S[:, valid][:, pc == k].sum(axis=1)
    return C / (C.sum(axis=1, keepdims=True) + 1e-9)


def _section_changes(C: np.ndarray, hb_db: np.ndarray) -> list[float]:
    """Seconds where the music changes: chroma + loudness novelty, comparing the 4 s before and after."""
    blk = int(round(0.5 / T_HOP))
    if len(C) <= blk * 18:
        return []
    cb = np.array([C[i:i + blk].mean(axis=0) for i in range(0, len(C) - blk, blk)])
    eb = np.array([hb_db[i:i + blk].mean() for i in range(0, len(C) - blk, blk)])
    k = 8
    nov = np.zeros(len(cb))
    for i in range(k, len(cb) - k):
        a, b = cb[i - k:i].mean(axis=0), cb[i:i + k].mean(axis=0)
        cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        nov[i] = (1 - cos) * 4 + abs(eb[i - k:i].mean() - eb[i:i + k].mean()) / 12
    pk = _peaks(nov, min_gap=k, thr=max(0.25, float(np.percentile(nov, 90))))
    return [round(float(i * 0.5), 2) for i in pk][:20]


def _tempo_and_beats(music: dict, perc: np.ndarray, perc90: float, music_segs: list[list[float]]) -> np.ndarray:
    beats = np.array([])
    env = perc - perc.mean()
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    ac /= ac[0] + 1e-9
    lo, hi = int(60 / 190 / T_HOP), int(60 / 60 / T_HOP)
    lag = lo + int(np.argmax(ac[lo:hi])) if hi < len(ac) else 0
    if lag and not music.get("no_beat") and perc90 < WEAK_PERC and ac[lag] < WEAK_BEAT:
        music["no_beat"] = True  # a pad or drone without drums: the onset curve is codec ripple
    if lag and not music.get("no_beat"):
        tempo = 60 / (lag * T_HOP)
        if tempo < 75:  # prefer the common 75-180 BPM octave
            tempo *= 2
            lag = max(1, lag // 2)
        music["bpm"] = round(float(tempo), 1)
        music["bpm_alternatives"] = [round(float(tempo) / 2, 1), round(float(tempo) * 2, 1)]
        music["beat_strength"] = round(float(ac[lag]), 3)
        phase = int(np.argmax([perc[p::lag].sum() for p in range(lag)]))
        snapped = []
        for g in np.arange(phase, len(perc), lag):
            a, b = max(0, g - 3), min(len(perc), g + 4)
            snapped.append(a + int(np.argmax(perc[a:b])))
        beats = np.array(snapped) * T_HOP
        inside = np.zeros_like(beats, bool)
        for a, b in music_segs:
            inside |= (beats >= a) & (beats <= b)
        beats = beats[inside]
    return beats


def _character(S: np.ndarray, Sh: np.ndarray, freqs: np.ndarray, share: np.ndarray, music_segs: list[list[float]],
               speech_segs: list[list[float]], music: dict) -> dict:
    """Rough sound of the music, measured where possible without the voice on top: brightness (spectral centroid
    of the harmonic part), drums (percussive share), and an energy level and mood hint from those plus the tempo.
    A hint for choosing a track of the same feel, not a genre: nve cannot name the song or the genre."""
    n = len(S)
    m = np.zeros(n, bool)
    for a, b in music_segs:
        m[int(a / T_HOP):int(b / T_HOP)] = True
    quiet = m.copy()
    for a, b in speech_segs:
        quiet[int(a / T_HOP):int(b / T_HOP)] = False
    use = quiet if quiet.sum() > 2 / T_HOP else m  # >= 2 s of music without speech, else all the music
    if use.sum() < 10:
        return {}
    H = Sh[use]
    centroid = float((H * freqs[None, :]).sum() / (H.sum() + 1e-9))
    drums = float(np.percentile(share[use], 90))  # hits fill few frames: the median would always be ~0
    bpm = music.get("bpm")
    strength = music.get("beat_strength") or 0.0
    clean = bool(quiet.sum() > 2 / T_HOP)
    # with speech on top, consonants look like drums: tempo and drums only count when the beat is clearly there
    beat_ok = bool(bpm) and not music.get("no_beat") and strength >= 0.2
    score = ((bpm - 90) / 40 + (drums - 0.08) * 8 + strength * 1.5) if beat_ok else (drums - 0.08) * 8 * clean
    energy = "high" if score > 1.2 else "low" if score < 0.2 else "medium"
    bright = "bright" if centroid > 2600 else "warm" if centroid < 1500 else "neutral"
    mood = {"high": {"bright": "upbeat, punchy", "neutral": "energetic", "warm": "driving, bold"},
            "medium": {"bright": "light, positive", "neutral": "steady, modern", "warm": "warm, confident"},
            "low": {"bright": "airy, soft", "neutral": "calm, minimal", "warm": "warm, mellow"}}[energy][bright]
    return {"brightness_hz": round(centroid), "brightness": bright, "drums": round(drums, 3), "clear_beat": beat_ok,
            "energy": energy, "mood_hint": mood, "measured_without_voice": clean,
            "confidence": "medium" if clean else "low (music only heard under the voice)"}


def analyze(path: str | Path, cut_times: list[float] | None = None) -> dict:
    """{has_audio, duration, voice{present, ratio}, music{present, ratio, segments, bpm, bpm_alternatives,
    beat_strength, beats[], no_beat?, section_changes}, cuts_on_beat, beat_chance, cuts_on_onset, onset_chance,
    beat_synced_edit}."""
    x = extract_audio(path)
    if x is None or len(x) < SR * 0.3:
        return {"has_audio": False}
    dur = len(x) / SR
    S = _stft(x)
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    Sh, Sp = hpss(S)
    frame_db = 10 * np.log10((S ** 2).mean(axis=1) + 1e-12)
    peak_db = float(np.percentile(frame_db, 99))
    silent = frame_db < peak_db - 45

    # speech and music-bed windows (1 s, every 0.5 s)
    band = (freqs > 300) & (freqs < 3400)
    sb = Sh[:, band].sum(axis=1)
    sb_db = 10 * np.log10(sb ** 2 + 1e-12)
    w1 = int(round(0.5 / T_HOP))
    local_max = np.array([sb_db[max(0, i - w1):i + w1].max() for i in range(len(sb_db))])
    dip = sb_db < local_max - 12
    harm_ratio = (Sh ** 2).sum(axis=1) / ((S ** 2).sum(axis=1) + 1e-12)
    share = (Sp ** 2).sum(axis=1) / ((S ** 2).sum(axis=1) + 1e-12)
    hb_db = 10 * np.log10(Sh.sum(axis=1) ** 2 + 1e-12)
    perc = np.maximum(0, np.diff(np.log1p(Sp.sum(axis=1)), prepend=0))
    win, step = int(round(1.0 / T_HOP)), int(round(0.5 / T_HOP))
    speech_w, music_w = [], []
    for s in range(0, max(1, len(sb) - win + 1), step):
        seg = sb[s:s + win]
        z = (seg - seg.mean()) / (seg.std() + 1e-9)
        mod = np.abs(np.fft.rfft(z))
        mf = np.fft.rfftfreq(len(z), T_HOP)
        syl = float(mod[(mf > 3) & (mf < 8)].sum() / (mod[(mf > 0.5) & (mf < 20)].sum() + 1e-9))
        voiced = float((~silent[s:s + win]).mean())
        gaps = float(dip[s:s + win].mean())
        speech_w.append(syl > 0.36 and voiced > 0.4 and 0.05 < gaps < 0.85)
        a, b = max(0, s - win), min(len(hb_db), s + 2 * win)
        g = dip[a:b] & (frame_db[a:b] > peak_db - 45)
        if g.sum() >= 0.08 * (b - a):  # between words the sound stays loud and tonal: a music bed
            bed = float(np.median(frame_db[a:b][g])) > peak_db - 40 and float(np.median(harm_ratio[a:b][g])) > 0.62
        else:
            bed = float(np.median(harm_ratio[a:b])) > 0.6 and float(np.percentile(frame_db[a:b], 10)) > peak_db - 35
        pe = perc[a:b] - perc[a:b].mean()
        ac = np.correlate(pe, pe, "full")[len(pe) - 1:]
        lo, hi = int(0.3 / T_HOP), min(len(ac) - 1, int(1.0 / T_HOP))
        beat_ac = float(ac[lo:hi].max() / (ac[0] + 1e-9)) if hi > lo and ac[0] > 0 else 0.0
        music_w.append(bool(bed or beat_ac > 0.35))
    speech_segs = _runs(np.array(speech_w), 0.5)
    music_segs = _runs(np.array(music_w), 0.5, min_len_s=1.5, merge_gap_s=1.0)
    speech_ratio = sum(b - a for a, b in speech_segs) / dur
    music_ratio = sum(b - a for a, b in music_segs) / dur

    music: dict = {"present": music_ratio > 0.25, "ratio": round(music_ratio, 3), "segments": music_segs[:40]}
    beats = np.array([])
    perc90 = float(np.percentile(share, 90))
    # the no-drums floor looks at the 97th percentile: sparse but clear hits (a kick every 0.6 s) fill under 10 %
    # of the frames, while a pad or drone stays near 1e-5 everywhere
    if music["present"] and float(np.percentile(share, 97)) < PERC_FLOOR:
        music["no_beat"] = True
    if music["present"]:
        beats = _tempo_and_beats(music, perc, perc90, music_segs)
        music["character"] = _character(S, Sh, freqs, share, music_segs, speech_segs, music)
        music["section_changes"] = _section_changes(_chroma(Sh, freqs), hb_db)
        music["beats"] = [round(float(b), 3) for b in beats[:MAX_BEATS]]

    out = {"has_audio": True, "duration": round(dur, 3),
           "voice": {"present": speech_ratio > 0.1, "ratio": round(speech_ratio, 3)}, "music": music}
    cuts = np.array([c for c in (cut_times or []) if c > 0.2])
    on = _peaks(perc, min_gap=int(0.1 / T_HOP), thr=float(np.percentile(perc, 80))) * T_HOP
    if len(cuts) and len(on):
        dmin = np.min(np.abs(cuts[:, None] - on[None, :]), axis=1)
        out["cuts_on_onset"] = round(float((dmin < 0.08).mean()), 3)
        out["onset_chance"] = round(float(min(1.0, len(on) / dur * 0.16)), 3)
    out["beat_synced_edit"] = False
    if len(cuts) and len(beats):
        db_ = np.min(np.abs(cuts[:, None] - beats[None, :]), axis=1)
        out["cuts_on_beat"] = round(float((db_ < 0.07).mean()), 3)
        chance = min(1.0, len(beats) / dur * 0.14)
        out["beat_chance"] = round(float(chance), 3)
        out["beat_synced_edit"] = bool(len(cuts) >= 4 and out["cuts_on_beat"] > max(0.5, chance * 1.8))
    return out
