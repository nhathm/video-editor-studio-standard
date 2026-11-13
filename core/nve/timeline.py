"""Source-time <-> output-time mapping. The cut engine and the planner share this math, so the
word timings Claude plans against are exactly the ones the render produces."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# Pure hesitation sounds. Deliberately NOT "à", "ạ", "ở" (real Vietnamese words).
FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm", "uhm", "umm",
           "ờ", "ừ", "ừm", "ừa", "ơ", "ầm", "ờm", "ơm"}


def seg_frames(src_in: float, src_out: float, speed: float, fps: int) -> int:
    return max(1, int(round((src_out - src_in) / speed * fps)))


def segments(video_track: list[dict], speed: float, fps: int) -> list[dict]:
    """Each kept range with its output offset and frame-exact output duration."""
    out, t = [], 0.0
    for r in video_track:
        sp = float(r.get("speed", speed))
        n = seg_frames(r["in"], r["out"], sp, fps)
        d = n / fps
        out.append({**r, "speed": sp, "frames": n, "out_start": round(t, 4), "out_dur": round(d, 4)})
        t += d
    return out


def total_duration(video_track: list[dict], speed: float, fps: int) -> float:
    return round(sum(s["out_dur"] for s in segments(video_track, speed, fps)), 3)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").strip())
    return re.sub(r"-{2,}$", "", text).strip()   # Scribe marks cut-off words with a trailing "--"


def is_filler(text: str) -> bool:
    return re.sub(r"[^\w]", "", text.lower()) in FILLERS


def corrections_path(transcript: Path) -> Path:
    t = Path(transcript)
    return t.with_name(f"{t.stem}.corrections.json")


def load_raw_words(transcript: Path) -> list[dict]:
    if not transcript or not Path(transcript).exists():
        return []
    data = json.loads(Path(transcript).read_text())
    words = data if isinstance(data, list) else data.get("words", [])
    return [w for w in words if w.get("type", "word") == "word" and w.get("start") is not None and w.get("end") is not None]


def apply_corrections(words: list[dict], fixes: list[dict]) -> tuple[list[dict], list[str]]:
    """Spelling fixes from the transcript review: [{"i": index, "from": original, "to": corrected}].
    Text only, timings never change. "to": "" deletes the word. A fix whose "from" no longer matches
    the word at "i" is skipped (the transcript changed), and reported."""
    out = [dict(w) for w in words]
    problems = []
    for f in fixes:
        i = f.get("i")
        if not isinstance(i, int) or not 0 <= i < len(out):
            problems.append(f"fix {f}: index out of range")
            continue
        have = clean_text(words[i].get("text", ""))
        if f.get("from") is not None and clean_text(f["from"]) != have:
            problems.append(f"fix #{i}: expected '{f['from']}' but the word is '{have}'; skipped")
            continue
        out[i]["text"] = f.get("to", "")
        out[i]["corrected_from"] = have
    return [w for w in out if w.get("text", "").strip()], problems


def silences_path(transcript: Path) -> Path:
    t = Path(transcript)
    return t.with_name(f"{t.stem}.silences.json")


def repair_timings(words: list[dict], holes: list[list[float]]) -> list[dict]:
    """Push word edges out of measured pauses. whisper often stretches a word across the pause
    before/after it, which would make cuts clip speech and captions run early."""
    out = []
    for w in words:
        s, e = w["start"], w["end"]
        for hs, he in holes:
            if e <= hs or s >= he:
                continue
            if s < hs and e > he:          # word spans the whole pause: keep its larger side
                if hs - s >= e - he:
                    e = hs
                else:
                    s = he
            elif s >= hs and e <= he:      # word inside a pause: it belongs right after it
                d = min(e - s, 0.4)
                s, e = he, he + d
            elif s < hs:
                e = hs
            else:
                s = he
        out.append({**w, "start": round(s, 3), "end": round(max(e, s + 0.05), 3)})
    return out


def load_words(transcript: Path) -> list[dict]:
    words = load_raw_words(transcript)
    if not words:
        return words
    sp = silences_path(transcript)
    if sp.exists():
        words = repair_timings(words, json.loads(sp.read_text()))
    cp = corrections_path(transcript)
    if cp.exists():
        words, _ = apply_corrections(words, json.loads(cp.read_text()).get("fixes", []))
    return words


def output_words(video_track: list[dict], transcripts: dict[str, list[dict]], speed: float, fps: int,
                 fixes: dict[str, str] | None = None, keep_fillers: bool = False) -> list[dict]:
    out: list[dict] = []
    for s in segments(video_track, speed, fps):
        for w in transcripts.get(s["src"], []):
            if w["end"] <= s["in"] or w["start"] >= s["out"]:
                continue
            text = clean_text(w.get("text", ""))
            if not text or (not keep_fillers and is_filler(text)):
                continue
            for a, b in (fixes or {}).items():
                text = re.sub(a, b, text)
            ws = (max(s["in"], w["start"]) - s["in"]) / s["speed"] + s["out_start"]
            we = (min(s["out"], w["end"]) - s["in"]) / s["speed"] + s["out_start"]
            we = min(we, s["out_start"] + s["out_dur"])
            if we <= ws:
                we = ws + 0.05
            out.append({"id": f"w{len(out)}", "text": text, "start": round(ws, 3), "end": round(we, 3), "src": s["src"]})
    return out


def subtract(ranges: list[list[float]], holes: list[tuple[float, float]], pad: float = 0.12,
             min_len: float = 0.25) -> list[list[float]]:
    """Remove silent intervals (from ffmpeg silencedetect) from keep-ranges, leaving `pad` of air
    on each side. Used when word timings are unreliable around pauses (whisper fills gaps)."""
    out = []
    for a, b in ranges:
        cur = a
        for s, e in sorted(holes):
            s2, e2 = s + pad, e - pad
            if e2 - s2 <= 0 or e2 <= cur or s2 >= b:
                continue
            if s2 - cur >= min_len:
                out.append([round(cur, 3), round(s2, 3)])
            cur = max(cur, e2)
        if b - cur >= min_len:
            out.append([round(cur, 3), round(b, 3)])
    return out


def speech_ranges(words: list[dict], src_dur: float, gap: float = 0.45, pad_in: float = 0.12, pad_out: float = 0.20,
                  drop_fillers: bool = True) -> list[list[float]]:
    """speech strategy: keep runs of words, split where the silence between words exceeds `gap`.
    Filler words are treated as silence, so 'ờ' between two sentences becomes a cut."""
    ws = [w for w in words if not (drop_fillers and is_filler(clean_text(w.get("text", ""))))]
    if not ws:
        return []
    runs, cur = [], [ws[0]]
    for a, b in zip(ws, ws[1:]):
        if b["start"] - a["end"] > gap:
            runs.append(cur)
            cur = []
        cur.append(b)
    runs.append(cur)
    ranges: list[list[float]] = []
    for r in runs:
        s, e = max(0.0, r[0]["start"] - pad_in), min(src_dur, r[-1]["end"] + pad_out)
        if ranges and s <= ranges[-1][1]:
            ranges[-1][1] = e
        else:
            ranges.append([round(s, 3), round(e, 3)])
    return ranges
