"""compose socket, ffmpeg + ASS engine. Needs only ffmpeg with libass and Pillow, so it runs in a
bare cloud sandbox. Same render plan as HyperFrames; simpler motion:
  captions  karaoke groups on an opaque pill, spoken words recoloured, keywords in accent
  stamps    big outlined text slammed in with \\t scale/rotate (Lottie emoji are skipped)
  cards     Pillow-drawn PNG card overlaid with alpha fades
  audio     cut audio + looped bgm + delayed SFX, limited to about -1 dBTP"""
from __future__ import annotations

import shutil
from pathlib import Path

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


def build_ass(plan: dict) -> str:
    W, H = plan["W"], plan["H"]
    s = W / 1080
    pal, font = plan["palette"], plan["font"]
    ink, acc, txt, spoken = (ass_color(pal[k]) for k in ("ink", "accent", "text", "spoken"))
    cap = plan["captions"]
    cap_size = int((cap["size"] if cap else 60 * s) * SIZE_K)
    cf, cb = ass_font(font["caption"])
    tf, tb = ass_font(font["title"])
    styles = [
        f"Style: Cap,{cf},{cap_size},{txt},{txt},{ass_color(pal['ink'], 0x20)},{ass_color(pal['ink'], 0x20)},"
        f"{cb},0,0,0,100,100,0,0,3,{int(14 * s)},0,8,{int(70 * s)},{int(70 * s)},{cap['top'] if cap else 0},1",
        f"Style: Stamp,{tf},{int(112 * s)},{txt},{txt},{ink},{acc},{tb},0,0,0,100,100,0,0,1,{max(3, int(10 * s))},{int(11 * s)},8,{int(30 * s)},{int(30 * s)},0,1",
    ]
    ev = []
    if cap:
        for g in cap["groups"]:
            ws, st, en = g["words"], g["start"], g["end"]

            def line(active: int) -> str:
                parts = []
                for wi, w in enumerate(ws):
                    if wi <= active:
                        col = acc if w["key"] else spoken
                        pop = r"\fscx112\fscy112" if (w["key"] and wi == active) else ""
                        parts.append(f"{{\\c{col}{pop}}}{esc(w['text'])}{{\\r}}")
                    else:
                        parts.append(esc(w["text"]))
                return " ".join(parts)
            first = ws[0]["start"]
            if first > st + 0.01:
                ev.append(f"Dialogue: 1,{ass_time(st)},{ass_time(first)},Cap,,0,0,0,,{{\\fad(80,0)}}{line(-1)}")
            for wi, w in enumerate(ws):
                a = max(w["start"], st)
                b = ws[wi + 1]["start"] if wi + 1 < len(ws) else en
                if b > a:
                    fade = r"{\fad(80,0)}" if wi == 0 and first <= st + 0.01 else ""
                    ev.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{fade}{line(wi)}")
    for stp in plan["stamps"]:
        st, en = stp["start"] + 0.08, stp["end"]
        dur_ms = int((en - st) * 1000)
        lines = str(stp["props"]["text"]).split("|")
        longest = max(len(x) for x in lines)
        fs = int(min((100 if len(lines) > 1 else 112) * s * float(stp["props"].get("scale") or 1), 1450 * s / max(longest, 1)) * SIZE_K)
        alt = stp["props"].get("alt")
        top = stp["top"] + (int(134 * s) if stp.get("emoji") else 0)
        body = []
        for li, x in enumerate(lines):
            if alt and li == len(lines) - 1:
                body.append(f"{{\\c{acc}\\4c{ink}}}{esc(x)}{{\\c{txt}\\4c{acc}}}")
            else:
                body.append(esc(x))
        tags = (f"{{\\an8\\pos({W // 2},{top})\\fs{fs}\\fscx230\\fscy230\\frz8\\alpha&HFF&"
                f"\\t(0,240,\\fscx100\\fscy100\\frz3\\alpha&H00&)\\t({max(0, dur_ms - 180)},{dur_ms},\\alpha&HFF&)}}")
        joined = "\\N".join(body)
        ev.append(f"Dialogue: 2,{ass_time(st)},{ass_time(en)},Stamp,,0,0,0,,{tags}{joined}")
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + "\n".join(styles) + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    return head + "\n".join(ev) + "\n"


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
