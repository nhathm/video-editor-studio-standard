import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nve import registry, storyboard as SB, timeline
from nve.compose_plan import caption_groups
from nve.engines.compose_ass import ass_color, ass_time, build_ass
from nve.paths import INSTALL_ROOT, NveError


# ── registry: layering, extends, no overriding core ──
def test_core_templates_resolve():
    t = registry.resolve("core:talking-head", "template")
    assert t["cut_strategy"] == "speech"
    assert t["defaults"]["style"]["look"] == "trong-tro"


def test_user_extends_and_patch(tmp_path):
    d = tmp_path / "custom" / "templates" / "mine"
    d.mkdir(parents=True)
    (d / "template.json").write_text(json.dumps({
        "id": "user:mine", "extends": "core:talking-head@^1",
        "patch": {"defaults.style.font.title": "Be Vietnam Pro"}, "label": {"vi": "Của tôi"}}))
    t = registry.resolve("user:mine", "template", tmp_path)
    assert t["defaults"]["style"]["font"]["title"] == "Be Vietnam Pro"
    assert t["defaults"]["style"]["font"]["caption"] == "Montserrat"   # inherited
    assert t["_chain"] == ["user:mine", "core:talking-head"]
    assert t["label"]["vi"] == "Của tôi"


def test_user_cannot_claim_core_namespace(tmp_path):
    d = tmp_path / "custom" / "templates" / "talking-head"
    d.mkdir(parents=True)
    (d / "template.json").write_text(json.dumps({"id": "core:talking-head"}))
    with pytest.raises(NveError, match="cannot use the 'core:' namespace"):
        registry.scan("template", tmp_path)


def test_major_version_mismatch():
    with pytest.raises(NveError, match="version"):
        registry.resolve("core:talking-head@^2", "template")


def test_fork(tmp_path):
    p = registry.fork("core:talking-head", "template", "shop", tmp_path)
    assert json.loads((p / "template.json").read_text())["extends"] == "core:talking-head"
    assert registry.resolve("user:shop", "template", tmp_path)["cut_strategy"] == "speech"


# ── timeline: the cut and the planner agree ──
WORDS = [{"text": t, "start": s, "end": e, "type": "word"} for t, s, e in [
    ("Xin", 1.0, 1.2), ("chào", 1.25, 1.5), ("ờ", 1.6, 1.9), ("các", 2.6, 2.8), ("bạn--", 2.85, 3.0), ("bạn", 3.05, 3.3)]]


def test_speech_ranges_treat_fillers_as_silence():
    rs = timeline.speech_ranges(WORDS, 10.0, gap=0.45)
    assert rs == [[0.88, 1.7], [2.48, 3.5]]


def test_output_words_speed_fillers_fixes():
    track = [{"src": "a", "in": 0.88, "out": 1.7}, {"src": "a", "in": 2.48, "out": 3.5}]
    ws = timeline.output_words(track, {"a": WORDS}, 1.0, 30, {"chào": "chao"})
    assert [w["text"] for w in ws] == ["Xin", "chao", "các", "bạn", "bạn"]   # filler dropped, "--" stripped
    seg = timeline.segments(track, 1.0, 30)
    assert seg[1]["out_start"] == pytest.approx(round(round(0.82 * 30) / 30, 4))
    fast = timeline.output_words(track, {"a": WORDS}, 1.25, 30)
    assert fast[0]["start"] == pytest.approx((1.0 - 0.88) / 1.25, abs=1e-3)


def test_segments_are_frame_exact():
    seg = timeline.segments([{"src": "a", "in": 0.0, "out": 1.01}], 1.15, 30)[0]
    assert seg["frames"] == round(1.01 / 1.15 * 30)
    assert seg["out_dur"] == pytest.approx(seg["frames"] / 30, abs=1e-4)


# ── storyboard validation ──
def _sb():
    return {"schema": "nve.storyboard/1", "template": "core:talking-head", "cut_strategy": "speech",
            "output": {"width": 1080, "height": 1920, "fps": 30},
            "sources": [{"id": "a", "path": "source/x.mov"}],
            "tracks": {"video": [{"src": "a", "in": 0, "out": 2}], "overlay": []}}


def test_validate_ok_and_errors():
    assert SB.validate(_sb()) == []
    bad = _sb()
    bad["tracks"]["video"].append({"src": "zz", "in": 3, "out": 2})
    bad["tracks"]["overlay"].append({"block": "core:stamp.slam", "start": 5, "end": 6})
    errs = " ".join(SB.validate(bad))
    assert "unknown source 'zz'" in errs and "must be after" in errs


def test_gate_reopen_cascades():
    sb = _sb()
    SB.set_gate(sb, "plan", "t1"); SB.set_gate(sb, "preview", "t2")
    SB.set_gate(sb, "plan", None)
    assert sb["gates"] == {"plan": None, "preview": None, "final": None}


# ── compose helpers ──
def test_caption_groups_split():
    ws = [{"text": f"w{i}{'.' if i == 2 else ''}", "start": i * 0.3, "end": i * 0.3 + 0.25} for i in range(8)]
    gs = caption_groups(ws, 3, 5, 10.0, {"w1"})
    assert [len(g["words"]) for g in gs] == [3, 5]
    assert gs[0]["words"][1]["key"] is True


def test_ass_helpers():
    assert ass_color("#1F2A44") == "&H00442A1F"
    assert ass_time(61.234) == "0:01:01.23"


def test_build_ass_has_events():
    plan = {"W": 1080, "H": 1920, "palette": {"ink": "#1F2A44", "accent": "#FFD84D", "text": "#FFFFFF", "spoken": "#9EE6FF"},
            "font": {"title": "Montserrat", "caption": "Montserrat"},
            "captions": {"top": 1480, "size": 60, "groups": [{"id": "cg0", "start": 0.0, "end": 1.0,
                         "words": [{"text": "Xin", "start": 0.0, "end": 0.4, "key": False},
                                   {"text": "chào", "start": 0.4, "end": 0.9, "key": True}]}]},
            "stamps": [{"start": 0.1, "end": 1.2, "top": 100, "props": {"text": "A|B", "alt": True}, "emoji": []}]}
    ass = build_ass(plan)
    assert ass.count("Dialogue:") == 3 and "\\N" in ass and "PlayResX: 1080" in ass


# ── install-folder guard hook ──
def _hook(payload: dict) -> int:
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(INSTALL_ROOT)}
    env.pop("NVE_DEV", None)
    return subprocess.run([sys.executable, str(INSTALL_ROOT / "hooks" / "guard_install_dir.py")],
                          input=json.dumps(payload), text=True, env=env, capture_output=True).returncode


def test_guard_blocks_install_writes(tmp_path):
    assert _hook({"tool_name": "Write", "tool_input": {"file_path": str(INSTALL_ROOT / "core" / "x.py")}}) == 2
    assert _hook({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "custom" / "x.py")}}) == 0
    assert _hook({"tool_name": "Bash", "tool_input": {"command": f"cp a.py '{INSTALL_ROOT}/templates/'"}}) == 2
    assert _hook({"tool_name": "Bash", "tool_input": {"command": f"'{INSTALL_ROOT}/skills/nve/bin/nve' doctor > /tmp/x"}}) == 0


# ── transcript review (L0 / whisper) ──
def test_apply_corrections_checks_original():
    ws = [{"text": "khá", "start": 0, "end": 0.3}, {"text": "insulin", "start": 0.3, "end": 0.8},
          {"text": "ừm", "start": 0.9, "end": 1.0}]
    out, probs = timeline.apply_corrections(ws, [{"i": 0, "from": "khá", "to": "kháng"},
                                                 {"i": 1, "from": "WRONG", "to": "x"},
                                                 {"i": 2, "from": "ừm", "to": ""}, {"i": 9, "to": "y"}])
    assert [w["text"] for w in out] == ["kháng", "insulin"]
    assert out[0]["corrected_from"] == "khá" and len(probs) == 2


def test_load_words_uses_sidecars(tmp_path):
    t = tmp_path / "a.json"
    t.write_text(json.dumps({"engine": "whisper", "words": [
        {"type": "word", "text": "Đây", "start": 9.7, "end": 11.3},     # whisper stretched over the pause 9.8-10.9
        {"type": "word", "text": "chứng", "start": 11.3, "end": 11.6}]}))
    timeline.silences_path(t).write_text(json.dumps([[9.8, 10.9]]))
    timeline.corrections_path(t).write_text(json.dumps({"fixes": [{"i": 1, "from": "chứng", "to": "trứng"}]}))
    ws = timeline.load_words(t)
    assert ws[0]["start"] == 10.9 and ws[1]["text"] == "trứng"


def test_subtract_silences():
    assert timeline.subtract([[0.0, 10.0]], [(4.0, 5.0)]) == [[0.0, 4.12], [4.88, 10.0]]
    assert timeline.subtract([[0.0, 2.0]], [(1.0, 1.2)]) == [[0.0, 2.0]]   # pause shorter than 2x pad: kept


# ── green screen ──
def test_background_layers_sections():
    from nve.background import layers
    ls = layers({"type": "sections", "sections": [{"start": 4.0, "colors": ["#111111", "#222222"], "scale": 0.9},
                                                   {"start": 0.0, "colors": ["#333333", "#444444"]}]}, 10.0)
    assert [(l["start"], l["end"]) for l in ls] == [(0.0, 4.0), (4.0, 10.0)] and ls[1]["scale"] == 0.9
    assert layers(None, 5)[0]["kind"] == "gradient"
    assert layers({"type": "color", "color": "#FFFFFF"}, 5)[0]["colors"] == ["#FFFFFF", "#FFFFFF"]


def test_background_png(tmp_path):
    from PIL import Image
    from nve.background import layers, png
    p = png(layers(None, 1)[0], 108, 192, tmp_path / "bg.png", dots=True)
    assert Image.open(p).size == (108, 192)


def test_garbage_rows_and_greenkey_math():
    import numpy as np
    from nve.engines.key import garbage_rows
    f = np.zeros((100, 70, 3), np.uint8)
    f[:20] = (200, 190, 180)        # wall above the screen
    f[20:] = (30, 160, 60)          # green screen
    assert garbage_rows(f, np) == 20


def test_ingest_detects_greenscreen(tmp_path):
    import shutil
    from nve.stages import detect_greenscreen
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    (tmp_path / "source").mkdir()
    (tmp_path / "work").mkdir()
    vid = tmp_path / "source" / "g.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x1D9E3A:s=108x192:d=2", "-vf",
                    "drawbox=x=34:y=60:w=40:h=132:color=0x203040:t=fill", str(vid)], check=True)
    g = detect_greenscreen(vid, {"kind": "video", "duration": 2.0})
    assert g["likely"] and g["screen"].startswith("#")


def test_retry_once_runs_twice_then_raises():
    import pytest
    from nve.util import retry_once
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first")
        return "ok"
    assert retry_once(flaky, "flaky") == "ok" and len(calls) == 2

    calls.clear()

    def broken():
        calls.append(1)
        raise RuntimeError("always")
    with pytest.raises(RuntimeError):
        retry_once(broken, "broken")
    assert len(calls) == 2

    calls.clear()

    def not_retried():
        calls.append(1)
        raise ValueError("bad input")
    with pytest.raises(ValueError):
        retry_once(not_retried, "x", on=(RuntimeError,))
    assert len(calls) == 1


def test_probe_url_treats_proxy_403_as_blocked(monkeypatch):
    import io
    import urllib.error
    import urllib.request
    from nve.env import probe_url

    def raiser(code):
        def f(*a, **k):
            raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
        return f
    monkeypatch.setattr(urllib.request, "urlopen", raiser(403))
    assert probe_url("https://x") is False
    monkeypatch.setattr(urllib.request, "urlopen", raiser(401))
    assert probe_url("https://x") is True

    def refused(*a, **k):
        raise urllib.error.URLError("Tunnel connection failed: 403 Forbidden")
    monkeypatch.setattr(urllib.request, "urlopen", refused)
    assert probe_url("https://x") is False

