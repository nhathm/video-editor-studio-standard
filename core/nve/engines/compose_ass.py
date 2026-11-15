"""compose socket, ffmpeg + ASS engine. Needs only ffmpeg with libass and Pillow, so it runs in a
bare cloud sandbox. Same render plan as HyperFrames; simpler motion:
  captions  karaoke groups on an opaque pill, spoken words recoloured, keywords in accent
  stamps    big outlined text slammed in with \\t scale/rotate (Lottie emoji are skipped)
  cards     Pillow-drawn PNG card overlaid with alpha fades
  audio     cut audio + looped bgm + delayed SFX, limited to about -1 dBTP"""
from __future__ import annotations

import shutil
from pathlib import Path

from nve.compose_plan import measurer, plain, rich
from nve.engines import Ctx, Engine, EngineFailed
from nve.paths import INSTALL_ROOT
from nve.util import duration, run


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _wrap(words: list[str], width_of, max_w: float) -> list[list[int]]:
    """Indices of words per line, greedy, never more than the width allows (a single long word gets its own line)."""
    lines, cur, cw, sp = [], [], 0.0, width_of(" ")
    for i, w in enumerate(words):
        ww = width_of(w)
        if cur and cw + sp + ww > max_w:
            lines.append(cur)
            cur, cw = [], 0.0
        cw = cw + (sp if cur else 0) + ww
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def _rect(x0: float, y0: float, x1: float, y1: float) -> str:
    w, h = int(x1 - x0), int(y1 - y0)
    return f"m 0 0 l {w} 0 l {w} {h} l 0 {h}"


def build_ass(plan: dict) -> str:
    W, H = plan["W"], plan["H"]
    s = W / 1080
    pal, font = plan["palette"], plan["font"]
    ink, acc, txt, spoken = (ass_color(pal[k]) for k in ("ink", "accent", "text", "spoken"))
    cap = plan["captions"]
    var = (cap or {}).get("variant", "pill")
    csz = cap["size"] if cap else int(60 * s)
    cap_size = measurer(font["caption"], csz)[1]
    cf, cb = ass_font(font["caption"])
    tf, tb = ass_font(font["title"])
    side = int((70 if var == "pill" else 86) * s)
    stroke = max(3, int(csz * 0.16))
    shadow = ass_color("#000000", 0x80)
    styles = [
        f"Style: Cap,{cf},{cap_size},{txt},{txt},{ass_color(pal['ink'], 0x20)},{ass_color(pal['ink'], 0x20)},"
        f"{cb},0,0,0,100,100,0,0,3,{int(14 * s)},0,8,{side},{side},{cap['top'] if cap else 0},1",
        f"Style: CapO,{cf},{cap_size},{txt},{txt},{ink},{shadow},{cb},0,0,0,100,100,0,0,1,{stroke * 0.55:.1f},{max(1, int(csz * 0.06))},8,{side},{side},{cap['top'] if cap else 0},1",
        f"Style: Stamp,{tf},{int(112 * s)},{txt},{txt},{ink},{acc},{tb},0,0,0,100,100,0,0,1,{max(3, int(10 * s))},{int(11 * s)},8,{int(30 * s)},{int(30 * s)},0,1",
        f"Style: Hook,{tf},{int(96 * s)},{txt},{txt},{ink},{shadow},{tb},0,0,0,100,100,0,0,1,{max(3, int(7 * s))},{max(1, int(6 * s))},8,0,0,0,1",
        f"Style: Box,{cf},{cap_size},{acc},{acc},{acc},{acc},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    ev = []
    if cap and var == "box":
        width_of = measurer(font["caption"], csz)[0]
        lh = int(csz * 1.18)
        pad = int(csz * 0.14)
        for g in cap["groups"]:
            ws, st, en = g["words"], g["start"], g["end"]
            if any(w.get("br") for w in ws):
                k = next(i for i, w in enumerate(ws) if w.get("br"))
                lines = [list(range(k + 1)), list(range(k + 1, len(ws)))]
            else:
                lines = _wrap([w["text"] for w in ws], width_of, W - 2 * side)
            first = ws[0]["start"]
            for k in range(len(ws) + (1 if first > st + 0.01 else 0)):
                active = k - 1 if first > st + 0.01 else k
                a = st if active < 0 else max(ws[active]["start"], st)
                b = (ws[0]["start"] if active < 0 else (ws[active + 1]["start"] if active + 1 < len(ws) else en))
                if b <= a:
                    continue
                fade = r"\fad(80,0)" if a <= st + 0.01 else ""
                for li, idx in enumerate(lines):
                    y = cap["top"] + li * lh
                    parts = []
                    for i in idx:
                        w = ws[i]
                        col = ink if i == active else (acc if (w["key"] and i < active) else txt)
                        bord = r"\bord0\shad0" if i == active else ""
                        parts.append(f"{{\\c{col}{bord}}}{esc(w['text'])}{{\\r}}")
                    ev.append(f"Dialogue: 2,{ass_time(a)},{ass_time(b)},CapO,,0,0,0,,{{\\an8\\pos({W // 2},{y}){fade}}}" + " ".join(parts))
                    if active in idx:
                        line_w = sum(width_of(ws[i]["text"]) for i in idx) + width_of(" ") * (len(idx) - 1)
                        x = W / 2 - line_w / 2 + sum(width_of(ws[i]["text"]) + width_of(" ") for i in idx[:idx.index(active)])
                        x0, x1 = x - pad, x + width_of(ws[active]["text"]) + pad
                        ev.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Box,,0,0,0,,{{\\an7\\pos({int(x0)},{int(y + csz * 0.06)})\\p1}}"
                                  f"{_rect(x0, 0, x1, csz * 1.12)}{{\\p0}}")
    elif cap:
        style = "Cap" if var == "pill" else "CapO"
        for g in cap["groups"]:
            ws, st, en = g["words"], g["start"], g["end"]

            def line(active: int) -> str:
                parts = []
                for wi, w in enumerate(ws):
                    if var == "pill":
                        lit = wi <= active
                        col = (acc if w["key"] else spoken) if lit else None
                    else:
                        col = acc if (wi == active or (w["key"] and wi < active)) else None
                    if col:
                        pop = r"\fscx112\fscy112" if (w["key"] and wi == active) else ""
                        parts.append(f"{{\\c{col}{pop}}}{esc(w['text'])}{{\\r}}")
                    else:
                        parts.append(esc(w["text"]))
                    if w.get("br"):
                        parts[-1] += "\\N"
                return " ".join(parts).replace("\\N ", "\\N")
            first = ws[0]["start"]
            enter = r"\fad(80,0)" if var != "pop" else r"\fad(60,0)\fscx55\fscy55\t(0,200,\fscx100\fscy100)"
            if first > st + 0.01:
                ev.append(f"Dialogue: 1,{ass_time(st)},{ass_time(first)},{style},,0,0,0,,{{{enter}}}{line(-1)}")
            for wi, w in enumerate(ws):
                a = max(w["start"], st)
                b = ws[wi + 1]["start"] if wi + 1 < len(ws) else en
                if b > a:
                    fade = f"{{{enter}}}" if wi == 0 and first <= st + 0.01 else ""
                    ev.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{fade}{line(wi)}")
    for stp in plan["stamps"]:
        st, en = stp["start"] + 0.08, stp["end"]
        dur_ms = int((en - st) * 1000)
        lines = plain(stp["props"]["text"]).split("|")
        longest = max(len(x) for x in lines)
        fs = int(min((100 if len(lines) > 1 else 112) * s * float(stp["props"].get("scale") or 1), 1450 * s / max(longest, 1)) * SIZE_K)
        alt = stp["props"].get("alt")
        top = stp["top"] + (int(134 * s) if stp.get("emoji") else 0)
        body = []
        for li, parts in enumerate(rich(stp["props"]["text"])):
            is_alt = alt and li == len(lines) - 1
            base, em = (f"\\c{acc}\\4c{ink}", f"\\c{txt}\\4c{ink}") if is_alt else (f"\\c{txt}\\4c{acc}", f"\\c{acc}\\4c{ink}")
            body.append("".join(f"{{{em if e else base}}}{esc(t)}" for t, e in parts) + f"{{\\c{txt}\\4c{acc}}}")
        tags = (f"{{\\an8\\q2\\pos({W // 2},{top})\\fs{fs}\\fscx230\\fscy230\\frz8\\alpha&HFF&"
                f"\\t(0,240,\\fscx100\\fscy100\\frz3\\alpha&H00&)\\t({max(0, dur_ms - 180)},{dur_ms},\\alpha&HFF&)}}")
        joined = "\\N".join(body)
        ev.append(f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Stamp,,0,0,0,,{tags}{joined}")
    for hk in plan.get("hooks", []):
        ev += _hook_events(hk, W, font, pal)
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + "\n".join(styles) + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    return head + "\n".join(ev) + "\n"


def _hook_events(hk: dict, W: int, font: dict, pal: dict) -> list[str]:
    """Hook title: words fade in one by one, then a marker sweeps in behind the *emphasised* words (a clipped
    rectangle growing left to right) and those words turn ink."""
    s = W / 1080
    st, en = hk["start"], hk["end"]
    lines = rich(hk["props"]["text"])
    fs = hk["size"]
    width_of, ass_fs = measurer(font["title"], fs)
    ink, txt, mk = ass_color(pal["ink"]), ass_color(pal["text"]), ass_color(hk["marker"])
    lh, pad = int(fs * 1.22), int(fs * 0.12)
    dur_ms = int((en - st) * 1000)
    ev, n_words, markers = [], 0, []
    for li, ln in enumerate(lines):
        y = hk["top"] + li * lh
        pieces = []   # (text, emphasised) per word, keeping marker groups
        for t, em in ln:
            for w in [w for w in t.split(" ") if w]:
                pieces.append((w, em))
        # a hard space more on each side of an emphasised run, so the marker does not touch the next word
        seps = ["" if i == 0 else (" \\h" if pieces[i - 1][1] != pieces[i][1] else " ") for i in range(len(pieces))]
        sw = [0.0 if not x_ else width_of(" ") * (2 if "h" in x_ else 1) for x_ in seps]
        line_w = sum(width_of(w) for w, _ in pieces) + sum(sw)
        x = W / 2 - line_w / 2
        out = []
        k = 0
        while k < len(pieces):
            x += sw[k]
            if pieces[k][1]:   # a run of emphasised words = one marker
                j = k
                while j < len(pieces) and pieces[j][1]:
                    j += 1
                run_w = sum(width_of(p_[0]) for p_ in pieces[k:j]) + sum(sw[k + 1:j])
                markers.append((x - pad, y + fs * 0.1, x + run_w + pad, y + fs * 1.18, len(markers)))
                for q in range(k, j):
                    out.append((pieces[q][0], int(60 * n_words), len(markers) - 1, seps[q]))
                    n_words += 1
                x += run_w
                k = j
                continue
            out.append((pieces[k][0], int(60 * n_words), None, seps[k]))
            n_words += 1
            x += width_of(pieces[k][0])
            k += 1
        t_mark = 60 * n_words + 120
        body = []
        for w, t0, m, sep in out:
            tag = f"\\fs{ass_fs}\\alpha&HFF&\\t({t0},{t0 + 200},\\alpha&H00&)"
            if m is not None:
                tm = t_mark + 140 * m + 80
                tag += f"\\c{txt}\\t({tm},{tm + 120},\\c{ink}\\bord0\\shad0)"
            body.append(f"{sep}{{{tag}}}{esc(w)}{{\\r}}")
        ev.append(f"Dialogue: 4,{ass_time(st)},{ass_time(en)},Hook,,0,0,0,,{{\\an8\\q2\\pos({W // 2},{y})\\fs{ass_fs}"
                  f"\\t({max(0, dur_ms - 180)},{dur_ms},\\alpha&HFF&)}}" + "".join(body))
    t_mark = 60 * n_words + 120
    for x0, y0, x1, y1, m in markers:
        tm = t_mark + 140 * m
        ev.append(f"Dialogue: 3,{ass_time(st)},{ass_time(en)},Box,,0,0,0,,{{\\an7\\pos({int(x0)},{int(y0)})\\c{mk}"
                  f"\\clip({int(x0)},{int(y0)},{int(x0) + 1},{int(y1)})\\t({tm},{tm + 300},\\clip({int(x0)},{int(y0)},{int(x1)},{int(y1)}))"
                  f"\\t({max(0, dur_ms - 180)},{dur_ms},\\alpha&HFF&)\\p1}}{_rect(x0, y0, x1, y1)}{{\\p0}}")
    return ev


SIZE_K = 1.12  # libass sizes glyphs smaller than CSS px at the same number


def ass_font(family: str) -> tuple[str, int]:
    """Prefer the static Black instance built by `nve fonts sync` (weight 900, like the HyperFrames
    look); fall back to the family name with faux bold."""
    d = INSTALL_ROOT / "packs" / "fonts" / family.replace(" ", "")
    if (d / f"{family.replace(' ', '')}-Black.ttf").exists():
        return f"{family} Black", 0
    return family, -1


def font_file(family: str) -> Path | None:
    d = INSTALL_ROOT / "packs" / "fonts" / family.replace(" ", "")
    for style in ("Black", "Bold"):
        if (d / f"{family.replace(' ', '')}-{style}.ttf").exists():
            return d / f"{family.replace(' ', '')}-{style}.ttf"
    files = sorted(d.glob("*.ttf")) if d.is_dir() else []
    return files[0] if files else None


def draw_card(card: dict, W: int, pal: dict, font: dict, out: Path) -> tuple[int, int]:
    from PIL import Image, ImageDraw, ImageFont
    s = W / 1080
    cw, pad, ih = int(480 * s), int(22 * s), int(250 * s)
    lab = card["props"].get("label") or ""
    ch = pad + ih + int(70 * s)
    img = Image.new("RGBA", (cw + 20, ch + int(60 * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    acc = tuple(int(pal["accent"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    ink = tuple(int(pal["ink"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    d.rounded_rectangle((10, 0, cw + 10, ch), radius=int(36 * s), fill=(255, 255, 255, 245), outline=acc, width=max(2, int(6 * s)))
    pic = Image.open(card["img"]).convert("RGBA")
    pic.thumbnail((cw - 2 * pad, ih))
    img.alpha_composite(pic, (10 + (cw - pic.width) // 2, pad + (ih - pic.height) // 2))
    if lab:
        ff = font_file(font["title"])
        f = ImageFont.truetype(str(ff), int(44 * s)) if ff else ImageFont.load_default()
        try:
            f.set_variation_by_axes([900])
        except Exception:
            pass
        tw = d.textlength(lab, font=f)
        lw, lh = int(tw + 60 * s), int(66 * s)
        x0, y0 = 10 + (cw - lw) // 2, ch - int(40 * s)
        d.rounded_rectangle((x0, y0, x0 + lw, y0 + lh), radius=int(18 * s), fill=ink)
        d.text((x0 + lw / 2, y0 + lh / 2), lab, font=f, fill=acc, anchor="mm")
    img.save(out)
    return img.width, img.height


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def draw_wall(wall: dict, W: int, H: int, out: Path, scale: int = 2) -> Path:
    """The wall picture cover-fitted to the frame (at `scale` x for a smooth zoom), with its tint."""
    from PIL import Image, ImageChops
    pic = Image.open(wall["img"]).convert("RGB")
    tw, th = W * scale, H * scale
    r = max(tw / pic.width, th / pic.height)
    pic = pic.resize((max(tw, int(pic.width * r)), max(th, int(pic.height * r))), Image.LANCZOS)
    x0, y0 = (pic.width - tw) // 2, (pic.height - th) // 2
    pic = pic.crop((x0, y0, x0 + tw, y0 + th))
    pr = wall["props"]
    if pr.get("tint"):
        tinted = ImageChops.multiply(pic, Image.new("RGB", pic.size, _hex(pr["tint"])))
        pic = Image.blend(pic, tinted, float(pr.get("tint_opacity") or 0.55))
    pic.save(out)
    return out


def draw_badge(wall: dict, W: int, font: dict, out: Path) -> tuple[int, int] | None:
    """The badge in the middle of a wall: rounded box, optional eye / play icon, text."""
    from PIL import Image, ImageDraw, ImageFont
    pr = wall["props"]
    if not pr.get("badge"):
        return None
    s = W / 1080
    ff = font_file(font["title"])
    f = ImageFont.truetype(str(ff), int(150 * s)) if ff else ImageFont.load_default()
    txt = str(pr["badge"])
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = probe.textlength(txt, font=f)
    icon = (pr.get("badge_icon") or "eye") if (pr.get("badge_icon") or "eye") in ("eye", "play") else None
    isz, gap, px, py = int(130 * s), int(22 * s), int(56 * s), int(26 * s)
    bw = int(tw + 2 * px + (isz + gap if icon else 0))
    bh = int(max(isz, 150 * s) + 2 * py)
    img = Image.new("RGBA", (bw + 20, bh + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, bw + 10, bh + 10), radius=int(40 * s), fill=_hex(pr.get("badge_color") or "#E53935"))
    x, cy = 10 + px, 10 + bh // 2
    lw = max(3, int(10 * s))
    if icon == "eye":
        d.ellipse((x, cy - isz * 0.32, x + isz, cy + isz * 0.32), outline="white", width=lw)
        rr = isz * 0.15
        d.ellipse((x + isz / 2 - rr, cy - rr, x + isz / 2 + rr, cy + rr), outline="white", width=lw)
    elif icon == "play":
        d.polygon([(x + isz * 0.25, cy - isz * 0.35), (x + isz * 0.25, cy + isz * 0.35), (x + isz * 0.85, cy)], fill="white")
    if icon:
        x += isz + gap
    d.text((x, cy), txt, font=f, fill="white", anchor="lm")
    img.save(out)
    return img.width, img.height


def _transitions(plan: dict, cur: str, n: int, inputs: list, vchain: list, work: Path) -> tuple[str, int]:
    """Cut effects on the whole picture: zoompan for zoom-punch / whip / shake, avgblur (whip), rgbashift + hue (glitch),
    a white layer fading in and out (flash)."""
    W, H, fps = plan["W"], plan["H"], plan["fps"]
    trs = plan.get("transitions") or []
    z, x, y = [], [], []
    for t in trs:
        a, d, ty = t["at"], t["duration"], t["type"]
        h = d / 2
        if ty == "zoom-punch":
            z.append(f"if(between(it,{a - 0.1:.3f},{a:.3f}),0.07*(it-{a - 0.1:.3f})/0.1,0)")
            z.append(f"if(between(it,{a:.3f},{a + d:.3f}),0.18*pow(1-(it-{a:.3f})/{d:.3f},3),0)")
        elif ty == "whip":
            z.append(f"if(between(it,{a - h:.3f},{a + h:.3f}),0.25,0)")
            x.append(f"if(between(it,{a - h:.3f},{a:.3f}),0.1*iw*pow((it-{a - h:.3f})/{h:.3f},2),"
                     f"if(between(it,{a:.3f},{a + h:.3f}),-0.1*iw*pow(1-(it-{a:.3f})/{h:.3f},2),0))")
        elif ty == "shake":
            z.append(f"if(between(it,{a:.3f},{a + d:.3f}),0.06,0)")
            x.append(f"if(between(it,{a:.3f},{a + d:.3f}),0.024*iw*sin((it-{a:.3f})*70)*(1-(it-{a:.3f})/{d:.3f}),0)")
            y.append(f"if(between(it,{a:.3f},{a + d:.3f}),0.012*ih*cos((it-{a:.3f})*55)*(1-(it-{a:.3f})/{d:.3f}),0)")
    if z or x or y:
        zz = "1+" + "+".join(z) if z else "1"
        xx = "(iw-iw/zoom)/2" + ("+" + "+".join(x) if x else "")
        yy = "(ih-ih/zoom)/2" + ("+" + "+".join(y) if y else "")
        vchain.append(f"{cur}zoompan=z='{zz}':x='max(0,min(iw-iw/zoom,{xx}))':y='max(0,min(ih-ih/zoom,{yy}))':d=1:s={W}x{H}:fps={fps}[tz]")
        cur = "[tz]"
    fx = []
    for t in trs:
        a, h, ty = t["at"], t["duration"] / 2, t["type"]
        on = f"enable='between(t,{a - h:.3f},{a + h:.3f})'"
        if ty == "whip":
            fx.append(f"avgblur=sizeX={max(4, int(36 * W / 1080))}:sizeY=1:{on}")
        elif ty == "glitch":
            fx.append(f"rgbashift=rh={-max(4, int(22 * W / 1080))}:bh={max(4, int(22 * W / 1080))}:{on}")
            fx.append(f"hue=h=90:s=2.5:{on}")
            fx.append(f"noise=alls=30:allf=t:{on}")
    if fx:
        vchain.append(f"{cur}{','.join(fx)}[tf]")
        cur = "[tf]"
    for t in trs:
        if t["type"] != "flash":
            continue
        a, d = t["at"], t["duration"]
        inputs += ["-f", "lavfi", "-i", f"color=c=white:s={W}x{H}:r={fps}:d={d:.3f}"]
        vchain.append(f"[{n}:v]format=rgba,fade=t=in:st=0:d={d / 2:.3f}:alpha=1,fade=t=out:st={d / 2:.3f}:d={d / 2:.3f}:alpha=1,"
                      f"colorchannelmixer=aa=0.9,setpts=PTS-STARTPTS+{max(0, a - d / 2):.3f}/TB[fl{n}]")
        vchain.append(f"{cur}[fl{n}]overlay=0:0:eof_action=pass[v{n}]")
        cur, n = f"[v{n}]", n + 1
    return cur, n


def _frame(f: dict, plan: dict, cur: str, n: int, inputs: list, vchain: list, work: Path) -> tuple[str, int]:
    from PIL import Image, ImageDraw, ImageFilter
    W, H, fps = plan["W"], plan["H"], plan["fps"]
    i, st, en, pr = f["i"], f["start"], f["end"], f["props"]
    fw, fh, r = f["w"], f["h"], f["radius"]
    b = max(3, int(8 * W / 1080)) if pr.get("border") else 0
    x, y = (W - fw) // 2, f["top"]
    # plate: shadow + border, drawn once
    m = int(40 * W / 1080)
    plate = Image.new("RGBA", (fw + 2 * m, fh + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(plate)
    d.rounded_rectangle((m, m + int(18 * W / 1080), m + fw, m + fh + int(18 * W / 1080)), radius=r, fill=(0, 0, 0, 120))
    plate = plate.filter(ImageFilter.GaussianBlur(int(22 * W / 1080)))
    if b:
        ImageDraw.Draw(plate).rounded_rectangle((m - b, m - b, m + fw + b, m + fh + b), radius=r + b, fill=_hex(pr["border"]) + (255,))
    plate.save(work / f"plate{i}.png")
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), radius=r, fill=255)
    mask.save(work / f"mask{i}.png")
    dur = en - st
    if f["is_video"]:
        inputs += ["-ss", f"{f['in']:.3f}", "-t", f"{dur + 0.1:.3f}", "-i", f["src"]]
    else:
        inputs += ["-loop", "1", "-t", f"{dur + 0.1:.3f}", "-i", f["src"]]
    inputs += ["-loop", "1", "-t", f"{dur + 0.1:.3f}", "-i", f"mask{i}.png", "-loop", "1", "-t", f"{dur + 0.1:.3f}", "-i", f"plate{i}.png"]
    fade = f"fade=t=in:st=0:d=0.22:alpha=1,fade=t=out:st={max(0.25, dur - 0.2):.3f}:d=0.2:alpha=1"
    shift = f"setpts=PTS-STARTPTS+{st:.3f}/TB"
    vchain.append(f"[{n}:v]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},fps={fps},format=rgba[fm{n}]")
    vchain.append(f"[{n + 1}:v]format=gray,scale={fw}:{fh}[mk{n}]")
    vchain.append(f"[fm{n}][mk{n}]alphamerge,{fade},{shift}[fa{n}]")
    vchain.append(f"[{n + 2}:v]format=rgba,fps={fps},{fade},{shift}[pl{n}]")
    yy = str(y)
    if (pr.get("anim") or "pop") == "slide-up":
        yy = f"{y}+max(0,({st + 0.35:.3f}-t)/0.35)*{int(H * 0.25)}"
    elif (pr.get("anim") or "pop") == "pop":
        yy = f"{y}+max(0,({st + 0.25:.3f}-t)/0.25)*{int(H * 0.04)}"
    on = f"enable='between(t,{st:.3f},{en:.3f})'"
    vchain.append(f"{cur}[pl{n}]overlay=x={x - m}:y='{yy}-{m}':eof_action=pass:{on}[v{n}]")
    vchain.append(f"[v{n}][fa{n}]overlay=x={x}:y='{yy}':eof_action=pass:{on}[v{n + 1}]")
    return f"[v{n + 1}]", n + 3


class Ass(Engine):
    id, capability = "ass", "compose"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        t = ctx.env["tools"]
        return (True, "") if t.get("ffmpeg") and t.get("libass") else (False, "ffmpeg without libass")

    def run(self, job: dict, ctx: Ctx) -> dict:
        plan = job["plan"]
        W, H, END = plan["W"], plan["H"], plan["duration"]
        work = Path(job["work"]) / "ass"
        if work.exists():
            shutil.rmtree(work)
        (work / "fonts").mkdir(parents=True)
        for fam in {plan["font"]["title"], plan["font"]["caption"]}:
            d = INSTALL_ROOT / "packs" / "fonts" / fam.replace(" ", "")
            for f in (d.glob("*.ttf") if d.is_dir() else []):
                if "[" not in f.name:  # static instances only: libass cannot pick weights from variable fonts
                    shutil.copy2(f, work / "fonts" / f.name)
        if plan["stamps"] and any(s.get("emoji") for s in plan["stamps"]):
            ctx.notes.append("compose.ass: animated emoji are not supported in this engine and were left out")
        (work / "subs.ass").write_text(build_ass(plan), encoding="utf-8")
        shutil.copy2(plan["video"], work / "cut.mp4")

        inputs = ["-i", "cut.mp4"]
        vchain, cur, n = [], "[0:v]", 1
        if plan.get("person"):  # green screen: background layers + keyed person instead of the cut picture
            from nve.background import png as bg_png
            pers = plan["person"]
            for i, ly in enumerate(plan["background"]["layers"]):
                f = bg_png(ly, W, H, work / f"bg{i}.png", plan["background"]["dots"])
                inputs += ["-loop", "1", "-t", f"{END:.3f}", "-r", str(plan["fps"]), "-i", f.name]
                if i == 0:
                    vchain.append(f"[{n}:v]format=yuv420p[b{n}]")
                else:
                    vchain.append(f"{cur}[{n}:v]overlay=0:0:enable='gte(t,{ly['start']:.3f})'[b{n}]")
                cur, n = f"[b{n}]", n + 1
            shutil.copy2(pers["path"], work / "person.webm")
            inputs += ["-c:v", "libvpx-vp9", "-i", "person.webm"]
            sc = pers["scale"]
            vchain.append(f"[{n}:v]format=rgba,scale=iw*{sc}:-2[pp]")
            vchain.append(f"{cur}[pp]overlay=x=(W-w)/2:y=H-h-{pers['y']}:format=auto[pv]")
            cur, n = "[pv]", n + 1
            if any(ly.get("scale") for ly in plan["background"]["layers"]):
                ctx.notes.append("compose.ass: per-section person zoom is not supported; one size used")
        cur, n = _transitions(plan, cur, n, inputs, vchain, work)
        for w in plan.get("walls", []):  # full-screen pictures under cards and text, zooming towards their focus
            st, en = w["start"], min(w["end"], END)
            frames = max(2, int(round((en - st) * plan["fps"])))
            draw_wall(w, W, H, work / f"wall{w['i']}.png")
            (z0, z1), (fx, fy) = w["zoom"], w["focus"]
            inputs += ["-loop", "1", "-t", f"{en - st + 0.2:.3f}", "-i", f"wall{w['i']}.png"]
            vchain.append(f"[{n}:v]zoompan=z='{z0}+({z1}-{z0})*on/{frames - 1}':x='max(0,min(iw-iw/zoom,{fx}*iw-iw/zoom/2))':y='max(0,min(ih-ih/zoom,{fy}*ih-ih/zoom/2))'"
                          f":d={frames}:s={W}x{H}:fps={plan['fps']},trim=end_frame={frames},setpts=PTS+{st:.3f}/TB[wz{n}]")
            vchain.append(f"{cur}[wz{n}]overlay=0:0:eof_action=pass:enable='between(t,{st:.3f},{en:.3f})'[v{n}]")
            cur, n = f"[v{n}]", n + 1
            size = draw_badge(w, W, plan["font"], work / f"badge{w['i']}.png")
            if size:
                bw, bh = size
                inputs += ["-loop", "1", "-t", f"{END:.3f}", "-i", f"badge{w['i']}.png"]
                vchain.append(f"[{n}:v]format=rgba,fade=t=in:st={st + 0.12:.3f}:d=0.2:alpha=1[bd{n}]")
                vchain.append(f"{cur}[bd{n}]overlay=x=({W}-{bw})/2:y=({H}-{bh})/2:enable='between(t,{st:.3f},{en:.3f})'[v{n}]")
                cur, n = f"[v{n}]", n + 1
        for c in plan["cards"]:
            png = work / f"card{c['i']}.png"
            cw, chh = draw_card(c, W, plan["palette"], plan["font"], png)
            inputs += ["-loop", "1", "-t", f"{END:.3f}", "-i", png.name]
            st, en = c["start"], c["end"]
            vchain.append(f"[{n}:v]format=rgba,fade=t=in:st={st:.3f}:d=0.25:alpha=1,fade=t=out:st={max(st, en - 0.22):.3f}:d=0.22:alpha=1[c{n}]")
            vchain.append(f"{cur}[c{n}]overlay=x=({W}-{cw})/2:y={c['top']}:enable='between(t,{st:.3f},{en:.3f})'[v{n}]")
            cur, n = f"[v{n}]", n + 1
        for f in plan.get("frames", []):  # B-roll in rounded frames
            cur, n = _frame(f, plan, cur, n, inputs, vchain, work)
        vchain.append(f"{cur}subtitles=subs.ass:fontsdir=fonts[vout]")

        achain, mix = [], ["[0:a]"]
        if plan["bgm"]:
            inputs += ["-stream_loop", "-1", "-i", plan["bgm"]["path"]]
            achain.append(f"[{n}:a]atrim=0:{END:.3f},afade=t=in:d=0.4,afade=t=out:st={max(0, END - 1.5):.3f}:d=1.5,"
                          f"volume={plan['bgm']['volume']}[bgm]")
            mix.append("[bgm]")
            n += 1
        for x in plan["sfx"]:
            d = min(END - x["at"], x.get("max") or 99, duration(Path(x["path"])))
            if d <= 0.05:
                continue
            inputs += ["-i", x["path"]]
            ms = int(x["at"] * 1000)
            achain.append(f"[{n}:a]atrim=0:{d:.3f},aformat=channel_layouts=stereo,adelay={ms}|{ms},volume={x['volume']}[{x['id']}]")
            mix.append(f"[{x['id']}]")
            n += 1
        achain.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-14:TP=-2:LRA=11,aresample=48000[aout]")
        fc = ";".join(vchain + achain)
        out = Path(job["out"]).resolve() if not job.get("snapshot_at") else work / "preview.mp4"
        crf, preset = ("26", "veryfast") if job.get("snapshot_at") else ("18", "medium")
        r = run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
                 "-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-t", f"{END:.3f}", "-movflags", "+faststart", str(out)], cwd=work, check=False)
        if r.returncode != 0:
            raise EngineFailed("ffmpeg/ASS render failed: " + (r.stderr or "")[-400:])
        if job.get("snapshot_at"):
            sd = Path(job["snapshot_dir"])
            sd.mkdir(parents=True, exist_ok=True)
            stills = []
            for t in job["snapshot_at"]:
                p = sd / f"at-{t:.2f}s.png"
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(out), "-frames:v", "1", str(p)])
                stills.append(str(p))
            return {"stills": stills}
        return {"out": str(out)}


ENGINES = [Ass]
