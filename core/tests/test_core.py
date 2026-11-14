import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from nve import registry, storyboard as SB, timeline
from nve import compose_plan
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


def test_workspace_remembered_by_init(tmp_path, monkeypatch):
    from nve import paths
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NVE_WORKSPACE", raising=False)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert paths.find_workspace(elsewhere) is None
    ws = tmp_path / "nve-studio"
    ws.mkdir()
    (ws / "studio.json").write_text("{}")
    paths.remember_workspace(ws)
    assert paths.find_workspace(elsewhere) == ws.resolve()



def test_resources_sparse_fetch_join_and_checksums(tmp_path, monkeypatch):
    import hashlib
    import json
    import shutil
    import subprocess

    import pytest
    from nve import resources
    from nve.paths import NveError
    blob = bytes(range(256)) * 100
    repo = tmp_path / "res"
    d = repo / "thing" / "v1"
    d.mkdir(parents=True)
    (repo / "other").mkdir()
    (repo / "other" / "big.bin").write_bytes(b"z" * 5000)
    parts = {"model.bin.part-aa": blob[:10000], "model.bin.part-ab": blob[10000:]}
    for n, b in parts.items():
        (d / n).write_bytes(b)
    (d / "config.json").write_text("{}")
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    files = {n: sha(b) for n, b in parts.items()}
    files.update({"config.json": sha(b"{}"), "model.bin": sha(blob)})
    cat = tmp_path / "resources.json"
    cat.write_text(json.dumps({"thing": {"version": "v1", "repo": f"file://{repo}", "path": "thing/v1",
                                         "join": {"model.bin": sorted(parts)}, "files": files}}))
    g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-q"); g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "m")
    monkeypatch.setattr(resources, "CATALOG", cat)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    out = resources.fetch("thing")
    assert (out / "model.bin").read_bytes() == blob and (out / "config.json").exists() and resources.is_cached("thing")
    assert not (out / "model.bin.part-aa").exists()
    shutil.rmtree(out)
    (d / "model.bin.part-ab").write_bytes(b"x" + blob[10001:])
    g("commit", "-qam", "bad")
    with pytest.raises(NveError):
        resources.fetch("thing")


# ── taste log ──
def _taste_sb(**kw):
    sb = {"schema": "nve.storyboard/1", "template": "core:talking-head", "cut_strategy": "speech",
          "output": {"aspect": "9:16", "width": 1080, "height": 1920, "fps": 30, "speed": 1.15},
          "style": {"caption": {"block": "core:caption.karaoke-pill", "group_max": 5}},
          "sources": [{"id": "a", "path": "a.mp4", "kind": "video"}],
          "tracks": {"video": [{"src": "a", "in": 0, "out": 30}], "overlay": [
              {"block": "core:stamp.slam", "start": t, "end": t + 1, "props": {"text": "X", "emoji": ["1f604"]}}
              for t in (1, 5, 9, 13)], "audio": [{"kind": "bgm", "asset": "lib:bgm/acoustic-01", "volume": 0.1}]}}
    sb.update(kw)
    return sb


def test_taste_add_apply_check_forget(tmp_path):
    from nve import taste
    r1 = taste.add(tmp_path, "nhiều stamp quá", maxes=["stamps_per_min=6"])
    r2 = taste.add(tmp_path, "chữ to lên", sets=["style.caption.size=0.07"], template="core:talking-head")
    r3 = taste.add(tmp_path, "tiếng ting sến", ban_sfx=["ting"], source="skill")
    assert [r1["id"], r2["id"], r3["id"]] == ["t1", "t2", "t3"]
    assert 'you said): "nhiều stamp quá"' in taste.describe(r1) and "skill rule" in taste.describe(r3)
    # only the right template gets the template rule
    assert len(taste.rules_for(taste.load(tmp_path), "core:product-ad", ["core:product-ad"])) == 2
    sb = _taste_sb()
    applied = taste.apply_defaults(sb, taste.rules_for(taste.load(tmp_path), "core:talking-head"))
    assert sb["style"]["caption"]["size"] == 0.07 and sb["style"]["ban_sfx"] == ["ting"] and len(applied) == 2
    dur = 30 / 1.15
    w = taste.check(sb, dur, tmp_path)
    assert len(w) == 1 and "stamps_per_min" in w[0] and "nhiều stamp quá" in w[0]   # 4 stamps in 26 s ≈ 9.2/min
    sb["tracks"]["audio"].append({"kind": "sfx", "asset": "lib:sfx/ting", "at": 2})
    assert any("SFX 'ting' is used" in x for x in taste.check(sb, dur, tmp_path))
    taste.set_active(tmp_path, "t1", False)
    taste.set_active(tmp_path, "t3", False)
    assert taste.check(sb, dur, tmp_path) == []
    with pytest.raises(NveError):
        taste.add(tmp_path, "x", sets=["gates.plan=1"])
    with pytest.raises(NveError):
        taste.add(tmp_path, "x", maxes=["zooms=2"])


def test_taste_metrics_count_block_sfx():
    from nve import taste
    m = taste.metrics(_taste_sb(), 60.0)
    assert m["stamps_per_min"] == 4 and m["emoji_per_min"] == 4 and m["caption_words_max"] == 5
    blk = registry.resolve("core:stamp.slam", "block")
    per = sum(1 for d in blk.get("default_sfx", []))  # every default fires: the stamps have emoji
    assert m["sfx_per_min"] == 4 * per and m["bgm_volume"] == 0.1


def test_taste_export_import_dedupes(tmp_path):
    from nve import taste
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    taste.add(a, "nhạc nhỏ thôi", maxes=["bgm_volume=0.08"])
    taste.add(a, "bỏ đi", ban_bgm=["acoustic-01"])
    taste.set_active(a, "t2", False)
    ex = taste.export(a)
    assert len(ex["rules"]) == 1 and "id" not in ex["rules"][0]
    assert taste.import_(b, ex)["added"] == ["t1"]
    assert taste.import_(b, ex)["added"] == []
    with pytest.raises(NveError):
        taste.import_(b, {"rules": []})


def test_banned_sfx_skipped_in_compose(tmp_path):
    sb = _taste_sb()
    words = []
    plan = compose_plan.build(sb, words, tmp_path / "cut.mp4", 26.0, tmp_path, None)
    names = {Path(s["path"]).stem for s in plan["sfx"]}
    assert names
    ban = sorted(names)[0]
    sb["style"]["ban_sfx"] = [ban]
    plan2 = compose_plan.build(sb, words, tmp_path / "cut.mp4", 26.0, tmp_path, None)
    assert ban not in {Path(s["path"]).stem for s in plan2["sfx"]} and len(plan2["sfx"]) < len(plan["sfx"])


# ── reference analysis: shot detection on synthetic clips with known answers ──
def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    # hard cuts at 2.0, 3.5, 5.5 and a 5-frame insert (5.5-5.667)
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x284:r=30:d=2", "-f", "lavfi", "-i", "color=c=0x2050C0:s=160x284:r=30:d=1.5",
        "-f", "lavfi", "-i", "mandelbrot=s=160x284:r=30", "-f", "lavfi", "-i", "color=c=0xC04020:s=160x284:r=30:d=0.15",
        "-f", "lavfi", "-i", "testsrc=s=160x284:r=30:d=2", "-filter_complex",
        "[2:v]trim=duration=2,setpts=PTS-STARTPTS[m];[0:v][1:v][m][3:v][4:v]concat=n=5:v=1[v]", "-map", "[v]",
        "-pix_fmt", "yuv420p", d / "cuts.mp4")
    # one moving picture with a 2-frame white flash at 1.5 s: no cut
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x284:r=30:d=3", "-vf",
        "drawbox=c=white:t=fill:enable='between(n,45,46)'", "-pix_fmt", "yuv420p", d / "flash.mp4")
    # fade to black and back in the middle of one moving picture, then a different picture
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x284:r=30:d=2", "-f", "lavfi", "-i", "mandelbrot=s=160x284:r=30",
        "-filter_complex", "[0:v]fade=t=out:st=1.5:d=0.5[a];[1:v]trim=duration=2,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.5[b];"
        "[a][b]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p", d / "fade.mp4")
    # same still picture, framing jumps 24 px at 1.5 s (talking-head jump cut / punch-in)
    _ff("-f", "lavfi", "-i", "testsrc2=s=240x284:r=30:d=0.04", "-frames:v", "1", d / "still.png")
    _ff("-loop", "1", "-t", "1.5", "-i", d / "still.png", "-loop", "1", "-t", "1.5", "-i", d / "still.png",
        "-filter_complex", "[0:v]crop=160:284:20:0,fps=30[a];[1:v]crop=160:284:44:0,fps=30[b];[a][b]concat=n=2:v=1[v]",
        "-map", "[v]", "-pix_fmt", "yuv420p", d / "jump.mp4")
    return d


def test_shots_hard_cuts_and_short_insert(synth):
    from nve.analyze import shots as S
    sh = S.shots_of(str(synth / "cuts.mp4"), 30)
    assert [s["start"] for s in sh] == [0.0, 2.0, 3.5, 5.5, 5.667]
    assert all(s["transition_in"] == "cut" for s in sh[1:])
    p = S.pace(sh, sh[-1]["end"])
    assert p["shots"] == 5 and p["shortest_s"] < 0.2 and p["transitions"] == {"cut": 4}


def test_shots_flash_is_not_a_cut(synth):
    from nve.analyze import shots as S
    assert len(S.shots_of(str(synth / "flash.mp4"), 30)) == 1


def test_shots_fade_and_jump_cut(synth):
    from nve.analyze import shots as S
    fade = S.shots_of(str(synth / "fade.mp4"), 30)
    assert len(fade) == 2 and abs(fade[1]["start"] - 2.0) < 0.1
    jump = S.shots_of(str(synth / "jump.mp4"), 30)
    assert len(jump) == 2 and abs(jump[1]["start"] - 1.5) < 0.05 and jump[1]["transition_in"] in ("jump", "cut")


def test_hsv_hist_matches_known_colours():
    from nve.analyze import shots as S
    red = np.zeros((4, 4, 3), np.uint8); red[..., 2] = 255
    blue = np.zeros((4, 4, 3), np.uint8); blue[..., 0] = 255
    assert S.bhattacharyya(S.hsv_hist(red), S.hsv_hist(red)) < 1e-3
    assert S.bhattacharyya(S.hsv_hist(red), S.hsv_hist(blue)) > 0.99


# ── reference analysis: beat / tempo on synthetic tracks ──
def _wav(path, x, sr=22050):
    import wave
    y = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes())
    return path


def _music(bpm=120.0, secs=20.0, drums=True, sr=22050):
    t = np.arange(int(secs * sr)) / sr
    x = 0.15 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277.2 * t) + np.sin(2 * np.pi * 329.6 * t))
    if drums:
        rng = np.random.default_rng(0)
        hit = rng.standard_normal(int(0.04 * sr)) * np.exp(-np.linspace(0, 8, int(0.04 * sr)))
        for k in np.arange(0, secs, 60 / bpm):
            i = int(k * sr)
            x[i:i + len(hit)] += 0.9 * hit[: len(x) - i]
    return x


def test_beat_tempo_grid_and_cuts_on_beat(tmp_path):
    from nve.analyze import beat
    p = _wav(tmp_path / "m120.wav", _music(120))
    on = beat.analyze(p, cut_times=[2.0, 4.0, 6.5, 9.0, 12.0, 15.5])
    m = on["music"]
    assert on["has_audio"] and m["present"] and abs(m["bpm"] - 120) <= 3
    gaps = np.diff(m["beats"])
    assert abs(float(np.median(gaps)) - 0.5) < 0.03 and min(abs(b - 2.0) for b in m["beats"]) < 0.05
    assert on["cuts_on_beat"] == 1.0 and on["beat_synced_edit"]
    off = beat.analyze(p, cut_times=[1.23, 3.71, 6.27, 8.81, 11.13, 14.37])
    assert off["cuts_on_beat"] < 0.4 and not off["beat_synced_edit"]


def test_beat_other_tempo_and_no_drums(tmp_path):
    from nve.analyze import beat
    m = beat.analyze(_wav(tmp_path / "m95.wav", _music(95)))["music"]
    assert abs(m["bpm"] - 95) <= 3 or abs(m["bpm"] - 190) <= 6
    pad = beat.analyze(_wav(tmp_path / "pad.wav", _music(drums=False)))["music"]
    assert pad.get("no_beat") or "bpm" not in pad or not pad["present"]
    silent = beat.analyze(_wav(tmp_path / "quiet.wav", np.zeros(22050 * 3)))
    assert not silent.get("music", {}).get("present", False)


# ── block core:media.wall ──
def test_media_wall_plan_offsets_and_drawings(tmp_path):
    from PIL import Image
    from nve.engines import compose_ass as CA
    from nve.engines.compose_hyperframes import _wall_offset
    Image.new("RGB", (400, 700), (40, 120, 200)).save(tmp_path / "wall.jpg")
    sb = _taste_sb()
    sb["tracks"]["overlay"] = [{"block": "core:media.wall", "start": 0.4, "end": 2.6,
                                "props": {"img": "wall.jpg", "focus": [1.4, 0.9], "zoom": [0.5, 2.2], "tint": "#B3121B", "badge": "140"}}]
    plan = compose_plan.build(sb, [], tmp_path / "cut.mp4", 8.0, tmp_path, None)
    w = plan["walls"][0]
    assert w["focus"] == [1.0, 0.9] and w["zoom"] == [1.0, 2.2]          # clamped into range
    assert any("whoosh" in Path(x["path"]).stem for x in plan["sfx"])
    assert _wall_offset(0.5, 0.5, 1.0, 1080, 1920) == (0, 0)
    assert _wall_offset(0.5, 0.5, 2.0, 1080, 1920) == (-540, -960)        # centre stays centred
    assert _wall_offset(1.0, 1.0, 2.0, 1080, 1920) == (-1080, -1920)      # clamped: no empty edge
    pic = Image.open(CA.draw_wall(w, 108, 192, tmp_path / "w.png"))
    assert pic.size == (216, 384) and pic.getpixel((10, 10))[0] < 40       # tint darkens the blue towards red
    size = CA.draw_badge(w, 1080, {"title": "Anton"}, tmp_path / "b.png")
    assert size and size[0] > size[1] > 100


def test_media_walls_back_to_back_are_joined(tmp_path):
    from PIL import Image
    Image.new("RGB", (40, 70)).save(tmp_path / "wall.jpg")
    sb = _taste_sb()
    sb["tracks"]["overlay"] = [{"block": "core:media.wall", "start": s, "end": e, "props": {"img": "wall.jpg"}}
                               for s, e in ((0.4, 2.7), (2.72, 4.3), (5.0, 6.0))]
    w = compose_plan.build(sb, [], tmp_path / "cut.mp4", 8.0, tmp_path, None)["walls"]
    assert w[0]["end"] == 2.72 and w[0].get("cut_out") and w[1].get("cut_in")
    assert not w[1].get("cut_out") and not w[2].get("cut_in")


def test_beat_character_energy_and_mood(tmp_path):
    from nve.analyze import beat
    fast = beat.analyze(_wav(tmp_path / "f.wav", _music(140)))["music"]["character"]
    pad = beat.analyze(_wav(tmp_path / "p.wav", _music(drums=False)))["music"]["character"]
    assert fast["energy"] in ("medium", "high") and pad["energy"] == "low"
    assert fast["drums"] > pad["drums"] and pad["mood_hint"] and fast["measured_without_voice"]


def test_beat_character_ignores_speech_like_hits_without_a_clear_beat(tmp_path):
    from nve.analyze import beat
    rng = np.random.default_rng(1)
    sr = 22050
    x = _music(drums=False) * 0.6
    for k in rng.uniform(0, 19.5, 120):          # irregular clicks, like consonants: no tempo
        i = int(k * sr)
        x[i:i + 300] += rng.standard_normal(300) * 0.5
    c = beat.analyze(_wav(tmp_path / "s.wav", x))["music"].get("character", {})
    assert not c.get("clear_beat") or c.get("energy") != "high"


def test_pro_commands_hidden_without_pro(monkeypatch, capsys):
    from nve import cli, pro
    monkeypatch.setattr(pro, "available", lambda: False)
    with pytest.raises(SystemExit):
        cli.main(["ref", "p", "x.mp4"])
    err = capsys.readouterr().err
    assert "invalid choice" in err and "Pro" not in err
    with pytest.raises(NveError) as e:
        pro.load("ref", "Reference style")
    assert "Do not mention it to the user" in str(e.value)
