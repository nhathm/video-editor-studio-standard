"""compose socket, HyperFrames engine (HTML + GSAP rendered frame by frame by Chrome).
Writes <work>/motion/{index.html, compositions/*.html, assets/} from a render plan, then
`hyperframes check` -> `render` (or `snapshot` for previews)."""
from __future__ import annotations

import html
import json
import os
import shutil
from pathlib import Path

from nve.engines import Ctx, Engine, EngineFailed
from nve.env import HYPERFRAMES_VERSION
from nve.paths import INSTALL_ROOT
from nve.compose_plan import plain, rich
from nve.util import duration, run

GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"
LOTTIE = "https://cdn.jsdelivr.net/npm/lottie-web@5.12.2/build/player/lottie.min.js"


def _env(ctx: Ctx) -> dict:
    return {**os.environ, "PATH": ctx.env["node"]["bin_dir"] + os.pathsep + os.environ.get("PATH", "")}


def _font_faces(families: set[str], assets_dir: Path) -> str:
    css = []
    for fam in sorted(families):
        d = INSTALL_ROOT / "packs" / "fonts" / fam.replace(" ", "")
        files = sorted(d.glob("*.ttf")) if d.is_dir() else []
        if not files:
            continue  # HyperFrames resolves its bundled families (Inter, Montserrat…) by name
        (assets_dir / "fonts").mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, assets_dir / "fonts" / f.name)
            weight = "100 900" if "[" in f.name else "400"
            style = "italic" if "Italic" in f.name else "normal"
            css.append(f'@font-face {{ font-family: "{fam}"; src: url("assets/fonts/{f.name}"); font-weight: {weight}; font-style: {style}; }}')
    return "\n".join(css)


EYE_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
           'stroke-linejoin="round"><path d="M1.5 12S5.5 4.5 12 4.5 22.5 12 22.5 12 18.5 19.5 12 19.5 1.5 12 1.5 12Z"/>'
           '<circle cx="12" cy="12" r="3.4"/></svg>')
PLAY_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12-7.5z"/></svg>'


def _wall_offset(fx: float, fy: float, z: float, W: int, H: int) -> tuple[int, int]:
    """Translation (px, with transform-origin 0 0) that brings the focus point to the centre at scale z, clamped so
    the picture always covers the frame."""
    tx = -min(max(fx * W * z - W / 2, 0), W * z - W)
    ty = -min(max(fy * H * z - H / 2, 0), H * z - H)
    return int(round(tx)), int(round(ty))


def write_project(plan: dict, motion: Path) -> None:
    W, H, END = plan["W"], plan["H"], plan["duration"]
    s = W / 1080
    pal, font = plan["palette"], plan["font"]
    INK, ACC, TXT = pal["ink"], pal["accent"], pal["text"]
    (motion / "compositions").mkdir(parents=True, exist_ok=True)
    A = motion / "assets"
    for sub in ("sfx", "img", "lottie"):
        (A / sub).mkdir(parents=True, exist_ok=True)
    cut = A / "cut.mp4"
    if cut.exists() or cut.is_symlink():
        cut.unlink()
    shutil.copy2(plan["video"], cut)

    # ── graphics: walls (under everything), cards, stamps ──
    Hh, J, LOT = [], [], {}
    for w in plan.get("walls", []):
        i, st, en, pr = w["i"], w["start"], w["end"], w["props"]
        img = A / "img" / f"wall{i}{Path(w['img']).suffix}"
        shutil.copy2(w["img"], img)
        fx, fy = w["focus"]
        z0, z1 = w["zoom"]
        tint = (f'<div class="wtint" style="background:{html.escape(pr["tint"])};opacity:{float(pr.get("tint_opacity") or 0.55)}"></div>'
                if pr.get("tint") else "")
        badge = ""
        if pr.get("badge"):
            icon = {"eye": EYE_SVG, "play": PLAY_SVG}.get(pr.get("badge_icon") or "eye", "")
            badge = (f'<div class="wbadge-w"><div id="wl{i}-b" class="wbadge" style="background:{html.escape(pr.get("badge_color") or "#E53935")}">'
                     f'{icon}<span>{html.escape(str(pr["badge"]))}</span></div></div>')
        Hh.append(f'    <div id="wl{i}" class="clip wall" data-start="{st:.3f}" data-duration="{en - st:.3f}">'
                  f'<img id="wl{i}-i" class="wimg" src="assets/img/{img.name}" alt="">'
                  f'{tint}{badge}</div>')
        if not w.get("cut_in"):
            J.append(f'tl.fromTo("#wl{i}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.1, ease: "none" }}, {st:.3f});')
        (x0, y0), (x1, y1) = _wall_offset(fx, fy, z0, W, H), _wall_offset(fx, fy, z1, W, H)
        J.append(f'tl.fromTo("#wl{i}-i", {{ scale: {z0}, x: {x0}, y: {y0} }}, {{ scale: {z1}, x: {x1}, y: {y1}, '
                 f'duration: {en - st:.3f}, ease: "power2.inOut" }}, {st:.3f});')
        if badge:
            J.append(f'tl.fromTo("#wl{i}-b", {{ opacity: 0, scale: 0.4 }}, {{ opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.2)" }}, {st + 0.12:.3f});')
        if not w.get("cut_out"):
            J.append(f'tl.fromTo("#wl{i}", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.08, ease: "none", immediateRender: false }}, {max(st, en - 0.08):.3f});')
    for c in plan["cards"]:
        i, st, en = c["i"], c["start"], c["end"]
        img = A / "img" / f"card{i}{Path(c['img']).suffix}"
        shutil.copy2(c["img"], img)
        lab = c["props"].get("label") or ""
        Hh.append(f'    <div id="cd{i}" class="clip cdw" data-start="{st:.3f}" data-duration="{en - st:.3f}" style="top:{c["top"]}px">'
                  f'<div id="cd{i}-i" class="card"><img src="assets/img/{img.name}" alt="">'
                  + (f'<div class="lab">{html.escape(lab)}</div>' if lab else "") + "</div></div>")
        J.append(f'tl.fromTo("#cd{i}-i", {{ opacity: 0, scale: 0.3, y: -80, rotation: -8 }}, {{ opacity: 1, scale: 1, y: 0, rotation: -2, duration: 0.45, ease: "back.out(2)" }}, {st:.3f});')
        if en - st > 1.4:
            J.append(f'tl.to("#cd{i}-i", {{ y: -12, rotation: 1, duration: {(en - st - 0.9) / 2:.3f}, ease: "sine.inOut", yoyo: true, repeat: 1 }}, {st + 0.5:.3f});')
        J.append(f'tl.to("#cd{i}-i", {{ opacity: 0, scale: 0.6, y: -40, duration: 0.22, ease: "power2.in" }}, {en - 0.22:.3f});')
    for stp in plan["stamps"]:
        i, st, en = stp["i"], stp["start"], stp["end"]
        lines = plain(stp["props"]["text"]).split("|")
        longest = max(len(x) for x in lines)
        fs = int(min((100 if len(lines) > 1 else 112) * s * float(stp["props"].get("scale") or 1), 1450 * s / max(longest, 1)))
        emo = ""
        for k, em in enumerate(stp.get("emoji", [])):
            dst = A / "lottie" / f"{em['cp']}.json"
            shutil.copy2(em["path"], dst)
            LOT[f"st{i}-e{k}"] = dst
            emo += f'<span class="lot"><i id="st{i}-e{k}" class="lotin"></i></span>'
        alt = stp["props"].get("alt")
        txt = "".join(f'<div class="sl{" alt" if alt and li == len(lines) - 1 else ""}" style="font-size:{fs}px;">'
                      + "".join(f'<span class="em">{html.escape(t)}</span>' if em else html.escape(t) for t, em in parts) + "</div>"
                      for li, parts in enumerate(rich(stp["props"]["text"])))
        Hh.append(f'    <div id="st{i}" class="clip stw" data-start="{st:.3f}" data-duration="{en - st:.3f}" style="top:{stp["top"]}px">'
                  f'<div id="st{i}-m" class="emr">{emo}</div><div id="st{i}-t" class="stt">{txt}</div></div>')
        if emo:
            J.append(f'tl.fromTo("#st{i}-m", {{ opacity: 0, scale: 0.2, y: 40 }}, {{ opacity: 1, scale: 1, y: 0, duration: 0.4, ease: "back.out(2.4)" }}, {st:.3f});')
        J.append(f'tl.fromTo("#st{i}-t", {{ opacity: 0, scale: 2.3, rotation: -8 }}, {{ opacity: 1, scale: 1, rotation: -3, duration: 0.24, ease: "power4.in" }}, {st + 0.08:.3f});')
        J.append(f'tl.to("#st{i}", {{ opacity: 0, y: -30, duration: 0.18, ease: "power2.in" }}, {en - 0.18:.3f});')
    for hk in plan.get("hooks", []):
        i, st, en = hk["i"], hk["start"], hk["end"]
        lines = rich(hk["props"]["text"])
        fs = hk["size"]
        body, words, k = [], 0, 0
        for ln in lines:
            row = []
            for t, em in ln:
                ws = [w for w in t.split(" ") if w]
                spans = " ".join(f'<span id="hk{i}-w{words + n}" class="hw">{html.escape(w)}</span>' for n, w in enumerate(ws))
                words += len(ws)
                if em:
                    row.append(f'<span class="hkm"><i id="hk{i}-m{k}" class="mk" style="background:{html.escape(hk["marker"])}"></i>'
                               f'<span id="hk{i}-t{k}" class="hkt">{spans}</span></span>')
                    k += 1
                elif spans:
                    row.append(spans)
            body.append(f'<div class="hl" style="font-size:{fs}px">{" ".join(row)}</div>')
        Hh.append(f'    <div id="hk{i}" class="clip hkw" data-start="{st:.3f}" data-duration="{en - st:.3f}" style="top:{hk["top"]}px">{"".join(body)}</div>')
        for n in range(words):
            J.append(f'tl.fromTo("#hk{i}-w{n}", {{ opacity: 0, y: {int(0.4 * fs)} }}, {{ opacity: 1, y: 0, duration: 0.22, ease: "back.out(2)" }}, {st + 0.06 * n:.3f});')
        t0 = st + 0.06 * words + 0.12
        for m in range(k):
            J.append(f'tl.fromTo("#hk{i}-m{m}", {{ scaleX: 0, rotation: -1.5 }}, {{ scaleX: 1, rotation: -1.5, duration: 0.3, ease: "power3.out" }}, {t0 + 0.14 * m:.3f});')
            J.append(f'tl.fromTo("#hk{i}-t{m}", {{ color: "{TXT}" }}, {{ color: "{INK}", duration: 0.12 }}, {t0 + 0.14 * m + 0.08:.3f});')
        J.append(f'tl.to("#hk{i}", {{ opacity: 0, y: -24, duration: 0.18, ease: "power2.in" }}, {max(st + 0.3, en - 0.18):.3f});')
    lottie_js = "    window.__hfLottie = window.__hfLottie || [];\n"
    for el, path in LOT.items():
        lottie_js += (f'    window.__hfLottie.push(lottie.loadAnimation({{ container: document.getElementById("{el}"), renderer: "svg", '
                      f'loop: true, autoplay: false, animationData: {path.read_text()} }}));\n')
    em = int(130 * s)
    (motion / "compositions/graphics.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; font-family: "{font['title']}", sans-serif; }}
    .wall {{ position: absolute; inset: 0; overflow: hidden; background: #000; }}
    .wimg {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 0 0; }}
    .wtint {{ position: absolute; inset: 0; mix-blend-mode: multiply; }}
    .wbadge-w {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }}
    .wbadge {{ display: flex; align-items: center; gap: {int(22 * s)}px; color: #fff; font-weight: 900; font-size: {int(150 * s)}px; line-height: 1; padding: {int(26 * s)}px {int(56 * s)}px; border-radius: {int(40 * s)}px; box-shadow: 0 0 0 {max(2, int(6 * s))}px rgba(255,255,255,.18), 0 30px 80px rgba(0,0,0,.45); }}
    .wbadge svg {{ width: {int(130 * s)}px; height: {int(130 * s)}px; }}
    .cdw {{ position: absolute; left: 0; right: 0; display: flex; justify-content: center; }}
    .card {{ position: relative; width: {int(480 * s)}px; background: rgba(255,255,255,.96); border-radius: {int(36 * s)}px; padding: {int(22 * s)}px {int(22 * s)}px {int(70 * s)}px; box-shadow: 0 20px 50px rgba(31,42,68,.3); border: {max(2, int(6 * s))}px solid {ACC}; }}
    .card img {{ display: block; width: 100%; height: {int(250 * s)}px; object-fit: contain; border-radius: {int(18 * s)}px; }}
    .lab {{ position: absolute; left: 50%; bottom: {-int(26 * s)}px; transform: translateX(-50%); background: {INK}; color: {ACC}; font-weight: 900; font-size: {int(44 * s)}px; padding: {int(8 * s)}px {int(30 * s)}px; border-radius: {int(18 * s)}px; white-space: nowrap; box-shadow: 0 8px 0 rgba(0,0,0,.18); }}
    .stw {{ position: absolute; left: {int(30 * s)}px; right: {int(30 * s)}px; display: flex; flex-direction: column; align-items: center; gap: 4px; }}
    .emr {{ display: flex; gap: {int(14 * s)}px; min-height: {em}px; }}
    .lot {{ display: inline-block; position: relative; width: {em}px; height: {em}px; }} .lotin {{ position: absolute; inset: 0; }}
    .stt {{ display: flex; flex-direction: column; align-items: center; }}
    .sl {{ font-weight: 900; line-height: 1.28; color: {TXT}; -webkit-text-stroke: {max(4, int(13 * s))}px {INK}; paint-order: stroke fill; text-shadow: 0 {int(11 * s)}px 0 {ACC}, 0 {int(22 * s)}px {int(34 * s)}px rgba(0,0,0,.3); white-space: nowrap; }}
    .sl.alt {{ color: {ACC}; text-shadow: 0 {int(11 * s)}px 0 {INK}, 0 {int(22 * s)}px {int(34 * s)}px rgba(0,0,0,.3); }}
    .sl .em {{ color: {ACC}; }} .sl.alt .em {{ color: {TXT}; }}
    .hkw {{ position: absolute; left: {int(40 * s)}px; right: {int(40 * s)}px; display: flex; flex-direction: column; align-items: center; gap: {int(6 * s)}px; }}
    .hl {{ font-weight: 900; line-height: 1.22; color: {TXT}; text-align: center; white-space: nowrap; -webkit-text-stroke: {max(3, int(10 * s))}px {INK}; paint-order: stroke fill; text-shadow: 0 {int(8 * s)}px {int(24 * s)}px rgba(0,0,0,.45); }}
    .hw {{ display: inline-block; }}
    .hkm {{ position: relative; display: inline-block; padding: 0 {int(14 * s)}px; }}
    .mk {{ position: absolute; left: 0; right: 0; top: 8%; bottom: 4%; border-radius: {int(14 * s)}px; transform-origin: 0 50%; }}
    .hkt {{ position: relative; -webkit-text-stroke: 0; text-shadow: none; }}
  </style>
  <div id="root" data-composition-id="graphics" data-width="{W}" data-height="{H}" data-layout-allow-overlap>
{chr(10).join(Hh)}
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join('    ' + j for j in J)}
{lottie_js}    window.__timelines["graphics"] = tl;
  </script>
</template>
""")

    # ── captions: pill (karaoke on a dark pill), outline, box (current word in a colour box), pop (big 1-3 words) ──
    cap = plan["captions"]
    var = (cap or {}).get("variant", "pill")
    CH, CJ = [], []
    if cap:
        for g in cap["groups"]:
            gid, st, en = g["id"], g["start"], g["end"]
            sp = " ".join(f'<span id="{gid}-w{wi}" class="cw">{html.escape(w["text"])}</span>' + ("<br>" if w.get("br") else "")
                          for wi, w in enumerate(g["words"]))
            CH.append(f'    <div id="{gid}" class="clip cgp" data-start="{st:.3f}" data-duration="{en - st:.3f}"><div id="{gid}-i" class="cgi">{sp}</div></div>')
            if var == "pop":
                CJ.append(f'tl.fromTo("#{gid}-i", {{ opacity: 0, scale: 0.55, y: {int(20 * s)} }}, {{ opacity: 1, scale: 1, y: 0, duration: 0.2, ease: "back.out(3)" }}, {st:.3f});')
            else:
                CJ.append(f'tl.fromTo("#{gid}-i", {{ opacity: 0, scale: 0.85 }}, {{ opacity: 1, scale: 1, duration: 0.14, ease: "back.out(2)" }}, {st:.3f});')
            ws = g["words"]
            for wi, w in enumerate(ws):
                sel, t0 = f"#{gid}-w{wi}", w["start"]
                t1 = ws[wi + 1]["start"] if wi + 1 < len(ws) else en
                if var == "pill":
                    CJ.append(f'tl.fromTo("{sel}", {{ color: "{TXT}" }}, {{ color: "{ACC if w["key"] else pal["spoken"]}", duration: 0.06 }}, {t0:.3f});')
                elif var == "box":
                    CJ.append(f'tl.set("{sel}", {{ backgroundColor: "{ACC}", color: "{INK}", webkitTextStrokeColor: "{ACC}" }}, {t0:.3f});')
                    if t1 < en or not w["key"]:
                        CJ.append(f'tl.set("{sel}", {{ backgroundColor: "rgba(0,0,0,0)", color: "{ACC if w["key"] else TXT}", webkitTextStrokeColor: "{INK}" }}, {max(t0 + 0.05, t1):.3f});')
                else:
                    CJ.append(f'tl.set("{sel}", {{ color: "{ACC}" }}, {t0:.3f});')
                    if not w["key"]:
                        CJ.append(f'tl.set("{sel}", {{ color: "{TXT}" }}, {max(t0 + 0.05, t1):.3f});')
                if w["key"]:
                    CJ.append(f'tl.fromTo("{sel}", {{ scale: 1 }}, {{ scale: 1.15, duration: 0.09, ease: "power2.out", yoyo: true, repeat: 1 }}, {t0:.3f});')
            if en < END:
                CJ.append(f'tl.to("#{gid}-i", {{ opacity: 0, duration: 0.08, ease: "power2.in" }}, {max(en - 0.08, st + 0.15):.3f});')
    csz = cap["size"] if cap else 60
    stroke = max(3, int(csz * 0.16))
    cap_css = {
        "pill": (f".cgi {{ background: {INK}e0; padding: {int(10 * s)}px {int(28 * s)}px {int(14 * s)}px; border-radius: {int(22 * s)}px; text-align: center; }}\n"
                 f"    .cw {{ display: inline-block; color: {TXT}; }}"),
        "outline": (f".cgi {{ text-align: center; }}\n"
                    f"    .cw {{ display: inline-block; color: {TXT}; -webkit-text-stroke: {stroke}px {INK}; paint-order: stroke fill; "
                    f"text-shadow: 0 {int(csz * 0.07)}px {int(csz * 0.2)}px rgba(0,0,0,.5); }}"),
        "box": (f".cgi {{ text-align: center; }}\n"
                f"    .cw {{ display: inline-block; color: {TXT}; padding: 0 {int(csz * 0.14)}px; margin: 0 -{int(csz * 0.06)}px; border-radius: {int(csz * 0.2)}px; "
                f"-webkit-text-stroke: {max(2, stroke - 2)}px {INK}; paint-order: stroke fill; text-shadow: 0 {int(csz * 0.06)}px {int(csz * 0.18)}px rgba(0,0,0,.45); }}"),
        "pop": (f".cgi {{ text-align: center; }}\n"
                f"    .cw {{ display: inline-block; color: {TXT}; -webkit-text-stroke: {stroke}px {INK}; paint-order: stroke fill; "
                f"text-shadow: 0 {int(csz * 0.08)}px 0 {INK}, 0 {int(csz * 0.12)}px {int(csz * 0.25)}px rgba(0,0,0,.45); }}"),
    }[var if var in ("pill", "outline", "box", "pop") else "pill"]
    side = int((70 if var == "pill" else 86) * s)
    (motion / "compositions/captions.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .cgp {{ position: absolute; left: {side}px; right: {side}px; top: {cap['top'] if cap else 0}px; display: flex; justify-content: center; font-family: "{font['caption']}", sans-serif; font-weight: 900; font-size: {csz}px; line-height: {1.2 if var == "pill" else 1.14}; }}
    {cap_css}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}">
{chr(10).join(CH)}
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join('    ' + x for x in CJ)}
    window.__timelines["captions"] = tl;
  </script>
</template>
""")

    # ── audio + root ──
    audio = []
    for k, x in enumerate(plan["sfx"]):
        src = Path(x["path"])
        dst = A / "sfx" / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        d = min(END - x["at"], x.get("max") or 99, duration(dst))
        if d <= 0.05:
            continue
        audio.append(f'      <audio id="{x["id"]}" class="clip" src="assets/sfx/{dst.name}" data-start="{x["at"]:.3f}" '
                     f'data-duration="{d:.3f}" data-volume="{x["volume"]}" data-track-index="{10 + k}"></audio>')
    bgm = ""
    if plan["bgm"]:
        run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", plan["bgm"]["path"], "-t", f"{END:.3f}", "-af",
             f"afade=t=in:d=0.4,afade=t=out:st={max(0, END - 1.5):.3f}:d=1.5", "-c:a", "aac", "-b:a", "192k", str(A / "bgm.m4a")])
        bgm = (f'      <audio id="bgm" class="clip" src="assets/bgm.m4a" data-start="0" data-duration="{END}" '
               f'data-volume="{plan["bgm"]["volume"]}" data-track-index="9"></audio>\n')
    # base layer: the cut video, or (green screen) background + keyed person + voice track
    base, root_js, base_css = "", "", ""
    if plan.get("person"):
        from nve.background import css as bg_css
        pers = plan["person"]
        shutil.copy2(pers["path"], A / "person.webm")
        run(["ffmpeg", "-v", "error", "-y", "-i", plan["video"], "-vn", "-c:a", "aac", "-b:a", "192k", str(A / "voice.m4a")])
        js = []
        for i, ly in enumerate(plan["background"]["layers"]):
            url = None
            if ly["kind"] == "image":
                dst = A / "img" / f"bg{i}{Path(ly['path']).suffix}"
                shutil.copy2(ly["path"], dst)
                url = f"assets/img/{dst.name}"
            base += f'      <div id="bg{i}" class="bg" style="{bg_css(ly, url)}{"" if i == 0 else "opacity:0;"}"></div>\n'
            if i:
                js.append(f'tl.to("#bg{i}", {{ opacity: 1, duration: 0.2, ease: "power2.out" }}, {max(0, ly["start"] - 0.1):.3f});')
            sc = ly.get("scale") or pers["scale"]
            js.append(f'tl.set("#pw", {{ scale: {sc}, y: {-pers["y"]} }}, {ly["start"]:.3f});')
        if plan["background"]["dots"]:
            base += '      <div id="bg-dots" class="dots"></div>\n'
            js.append(f'tl.fromTo("#bg-dots", {{ backgroundPosition: "0px 0px" }}, {{ backgroundPosition: "0px -320px", duration: {END}, ease: "none" }}, 0);')
        base += (f'      <div id="pw" class="pw"><video id="person" class="clip" src="assets/person.webm" data-start="0" '
                 f'data-duration="{END}" data-track-index="2" muted></video></div>\n'
                 f'      <audio id="voice" class="clip" src="assets/voice.m4a" data-start="0" data-duration="{END}" data-volume="1" data-track-index="3"></audio>\n')
        root_js = "\n".join("      " + x for x in js) + "\n"
        base_css = (".bg { position: absolute; inset: 0; }\n"
                    f"      .dots {{ position: absolute; inset: 0; background-image: radial-gradient(rgba(255,255,255,.45) {max(1, int(3 * s))}px, transparent {max(1.5, 3.5 * s)}px); background-size: {int(46 * s)}px {int(46 * s)}px; }}\n"
                    "      .pw { position: absolute; inset: 0; transform-origin: 50% 100%; }\n"
                    "      #person { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }")
    else:
        base = (f'      <video id="vid" class="clip" src="assets/cut.mp4" data-start="0" data-duration="{END}" data-track-index="1" '
                f'data-has-audio="true" data-volume="1"></video>\n')
    # B-roll in rounded frames (between the base video and the graphics)
    frames_html, fjs = "", []
    for f in plan.get("frames", []):
        i, st, en, pr = f["i"], f["start"], f["end"], f["props"]
        if f["is_video"]:
            dst = A / "img" / f"frame{i}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{f['in']:.3f}", "-t", f"{en - st + 0.1:.3f}", "-i", f["src"], "-an",
                 "-vf", f"scale={f['w']}:{f['h']}:force_original_aspect_ratio=increase,crop={f['w']}:{f['h']},fps={plan['fps']},format=yuv420p",
                 "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", str(dst)])
            media = (f'<video id="frv{i}" class="clip frm" src="assets/img/{dst.name}" data-start="{st:.3f}" data-duration="{en - st:.3f}" '
                     f'data-track-index="{40 + i}" muted></video>')
        else:
            dst = A / "img" / f"frame{i}{Path(f['src']).suffix}"
            shutil.copy2(f["src"], dst)
            media = f'<img class="frm" src="assets/img/{dst.name}" alt="">'
        border = f"border: {max(3, int(8 * s))}px solid {html.escape(pr['border'])};" if pr.get("border") else ""
        frames_html += (f'      <div id="fr{i}" class="frw" style="left:{(W - f["w"]) // 2}px;top:{f["top"]}px;width:{f["w"]}px;height:{f["h"]}px;'
                        f'border-radius:{f["radius"]}px;{border}">{media}</div>\n')
        anim = pr.get("anim") or "pop"
        if anim == "slide-up":
            fjs.append(f'tl.fromTo("#fr{i}", {{ opacity: 0, y: {int(H * 0.25)} }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }}, {st:.3f});')
        elif anim == "fade":
            fjs.append(f'tl.fromTo("#fr{i}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.25, ease: "none" }}, {st:.3f});')
        else:
            fjs.append(f'tl.fromTo("#fr{i}", {{ opacity: 0, scale: 0.55, rotation: -5 }}, {{ opacity: 1, scale: 1, rotation: -1.5, duration: 0.4, ease: "back.out(1.8)" }}, {st:.3f});')
        fjs.append(f'tl.to("#fr{i}", {{ opacity: 0, scale: 0.85, duration: 0.2, ease: "power2.in" }}, {max(st + 0.3, en - 0.2):.3f});')
    # transitions at cut points: the whole picture (#stage) moves, the cut itself stays where it is
    tjs, flash = [], False
    for t in plan.get("transitions", []):
        at, d, ty = t["at"], t["duration"], t["type"]
        if ty == "zoom-punch":
            tjs.append(f'tl.to("#stage", {{ scale: 1.07, duration: 0.1, ease: "power2.in" }}, {max(0, at - 0.1):.3f});')
            tjs.append(f'tl.fromTo("#stage", {{ scale: 1.18 }}, {{ scale: 1, duration: {d:.3f}, ease: "power3.out", immediateRender: false }}, {at:.3f});')
        elif ty == "flash":
            flash = True
            tjs.append(f'tl.fromTo("#tflash", {{ opacity: 0 }}, {{ opacity: 0.9, duration: {d / 2:.3f}, ease: "power1.in" }}, {max(0, at - d / 2):.3f});')
            tjs.append(f'tl.to("#tflash", {{ opacity: 0, duration: {d / 2:.3f}, ease: "power1.out" }}, {at:.3f});')
        elif ty == "whip":
            tjs.append(f'tl.to("#stage", {{ x: {-int(W * 0.1)}, scale: 1.25, filter: "blur(16px)", duration: {d / 2:.3f}, ease: "power2.in" }}, {max(0, at - d / 2):.3f});')
            tjs.append(f'tl.fromTo("#stage", {{ x: {int(W * 0.1)}, scale: 1.25, filter: "blur(16px)" }}, {{ x: 0, scale: 1, filter: "blur(0px)", '
                       f'duration: {d / 2:.3f}, ease: "power2.out", immediateRender: false }}, {at:.3f});')
        elif ty == "glitch":
            steps = [(-24, "hue-rotate(90deg) saturate(3)"), (18, "contrast(1.8) hue-rotate(-70deg)"), (-10, "invert(0.15) saturate(4)"),
                     (28, "hue-rotate(160deg) contrast(1.5)"), (-14, "saturate(2.5)"), (0, "none")]
            for k, (dx, flt) in enumerate(steps):
                tjs.append(f'tl.set("#stage", {{ x: {int(dx * s)}, scale: {1.06 if dx else 1}, filter: "{flt}" }}, {max(0, at - d / 2 + k * d / len(steps)):.3f});')
        elif ty == "shake":
            amp = [26, -22, 18, -14, 10, -7, 4, -2, 0]
            tjs.append(f'tl.set("#stage", {{ scale: 1.06 }}, {at:.3f});')
            for k, a in enumerate(amp):
                tjs.append(f'tl.to("#stage", {{ x: {int(a * s)}, y: {int(-a * 0.6 * s)}, rotation: {a * 0.04:.2f}, scale: {1.06 if a else 1}, '
                           f'duration: {d / len(amp):.3f}, ease: "none" }}, {at + k * d / len(amp):.3f});')
    if flash:
        frames_html += '      <div id="tflash" style="position:absolute;inset:0;background:#fff;opacity:0;z-index:4;"></div>\n'
    root_js += "".join("      " + x + "\n" for x in fjs + tjs)
    faces = _font_faces({font["title"], font["caption"]}, A)
    (motion / "index.html").write_text(f"""<!doctype html>
<html lang="vi">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="{GSAP}"></script>
    <script src="{LOTTIE}"></script>
    <style>
{faces}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; }}
      #vid {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
      {base_css}
      #graphics {{ position: absolute; inset: 0; z-index: 5; }}
      #captions {{ position: absolute; inset: 0; z-index: 6; }}
      #stage {{ position: absolute; inset: 0; overflow: hidden; transform-origin: 50% 50%; }}
      .frw {{ position: absolute; z-index: 4; overflow: hidden; opacity: 0; box-shadow: 0 {int(24 * s)}px {int(60 * s)}px rgba(0,0,0,.45); background: #000; }}
      .frm {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-fps="{plan['fps']}" data-start="0" data-duration="{END}" data-width="{W}" data-height="{H}">
      <div id="stage">
{base}      </div>
{frames_html}      <div id="graphics" data-composition-id="graphics" data-composition-src="compositions/graphics.html" data-start="0" data-duration="{END}" data-track-index="4" data-width="{W}" data-height="{H}"></div>
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{END}" data-track-index="5" data-width="{W}" data-height="{H}"></div>
{bgm}{chr(10).join(audio)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{root_js}      tl.set({{}}, {{}}, {END});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
""")


class HyperFrames(Engine):
    id, capability = "hyperframes", "compose"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        return (True, "") if ctx.env.get("node") else (False, "node >= 22 not found")

    def _cli(self, ctx: Ctx, *args: str, timeout: float = 3600):
        from nve.env import npx
        return npx(ctx.env["node"], list(args), timeout=timeout)

    def run(self, job: dict, ctx: Ctx) -> dict:
        motion = Path(job["work"]) / "motion"
        if not (motion / "hyperframes.json").exists():
            motion.mkdir(parents=True, exist_ok=True)
            r = self._cli(ctx, "init", str(motion), "--example", "blank", "--non-interactive", "--skip-skills", timeout=300)
            if r.returncode != 0:
                raise EngineFailed("hyperframes init failed: " + (r.stderr or r.stdout)[-300:])
        write_project(job["plan"], motion)
        r = self._cli(ctx, "check", str(motion), "--json", timeout=300)
        try:
            chk = json.loads(r.stdout[r.stdout.find("{"):]) if "{" in (r.stdout or "") else {}
        except json.JSONDecodeError:
            chk = {}
        errs = [x for x in (chk.get("errors") or chk.get("issues") or []) if (x.get("severity", "error") == "error")] if isinstance(chk, dict) else []
        if r.returncode != 0 and errs:
            raise EngineFailed("hyperframes check: " + "; ".join(str(e.get("message", e))[:120] for e in errs[:5]))
        if job.get("snapshot_at"):
            out_dir = Path(job["snapshot_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            at = ",".join(f"{t:.2f}" for t in job["snapshot_at"])
            r = self._cli(ctx, "snapshot", str(motion), "--at", at, "--no-end", "--keep", "-o", str(out_dir), timeout=900)
            if r.returncode != 0:
                raise EngineFailed("hyperframes snapshot failed: " + (r.stderr or r.stdout)[-400:])
            shots = sorted(out_dir.glob("at-*.png"), key=lambda p: float(p.stem[3:].rstrip("s")))
            return {"stills": [str(p) for p in shots]}
        out = Path(job["out"])
        r = self._cli(ctx, "render", str(motion), "-o", str(out), "--skill", "nve", timeout=7200)
        if r.returncode != 0 or not out.exists():
            raise EngineFailed("hyperframes render failed: " + (r.stderr or r.stdout)[-400:])
        return {"out": str(out), "project": str(motion)}


ENGINES = [HyperFrames]
