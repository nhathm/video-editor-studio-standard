"""cut socket, ffmpeg engine. Follows the video-use hard rules:
per-segment extract then lossless concat, 30 ms audio fades at every boundary, frame-exact
segment lengths shared with nve.timeline, HDR -> SDR tonemap, loudnorm to -14 LUFS."""
from __future__ import annotations

import subprocess
from pathlib import Path

from nve.engines import Ctx, Engine, EngineFailed
from nve.looks import ffmpeg_filter, numpy_pipeline
from nve.util import log, run

TONEMAP = "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"


def atempo_chain(speed: float) -> str:
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    if abs(s - 1.0) > 1e-6:
        parts.append(f"atempo={s:.5f}")
    return ",".join(parts)


class FfmpegCut(Engine):
    id, capability = "ffmpeg", "cut"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        return (True, "") if ctx.env["tools"].get("ffmpeg") else (False, "ffmpeg missing")

    def run(self, job: dict, ctx: Ctx) -> dict:
        W, H, FPS = job["width"], job["height"], job["fps"]
        proxy = job.get("proxy", False)
        crf, preset = ("28", "ultrafast") if proxy else ("16", "medium")
        work = Path(job["work"])
        work.mkdir(parents=True, exist_ok=True)
        grade = numpy_pipeline(job.get("look", "none"), job.get("skin", False), ctx.env.get("opencv", False))
        if grade is None and job.get("skin") and not ctx.env.get("opencv"):
            ctx.notes.append("skin retouch skipped: opencv not available")
        fit = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1"
        if job.get("flip"):  # front camera mirrors the picture (text on products reads backwards)
            fit += ",hflip"
        vlist, alist = [], []
        for i, s in enumerate(job["segments"]):
            n, d, sp = s["frames"], s["out_dur"], s["speed"]
            src_d = s["out"] - s["in"]
            vo, ao = work / f"v{i:03d}.mp4", work / f"a{i:03d}.wav"
            pre = TONEMAP if s.get("hdr") else ""
            if s["kind"] == "image":
                inp = ["-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", s["path"]]
                vf = f"{fit},fps={FPS}"
            else:
                inp = ["-ss", f"{s['in']:.3f}", "-t", f"{src_d + 0.15:.3f}", "-i", s["path"]]
                vf = f"{pre}setpts=(PTS-STARTPTS)/{sp:.5f},fps={FPS},{fit}"
            enc = ["-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(FPS)]
            if grade is None:
                look = ffmpeg_filter(job.get("look", "none"))
                run(["ffmpeg", "-v", "error", "-y", *inp, "-vf", vf + (f",{look}" if look else "") + ",format=yuv420p",
                     "-frames:v", str(n), "-an", *enc, str(vo)])
                got = int(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", str(vo)]).stdout.strip() or 0)
                if got < n:  # source ended early: hold the last frame (tpad) so A/V lengths match
                    tmp = vo.with_suffix(".pad.mp4")
                    run(["ffmpeg", "-v", "error", "-y", "-i", str(vo), "-vf", f"tpad=stop_mode=clone:stop={n - got}",
                         "-frames:v", str(n), *enc, str(tmp)])
                    tmp.replace(vo)
            else:
                self._pipe(inp, vf, n, W, H, FPS, enc, vo, grade)
            if s.get("has_audio") and s["kind"] != "image":
                af = ",".join(x for x in (atempo_chain(sp), "aresample=48000", "aformat=channel_layouts=stereo",
                                          "afade=t=in:d=0.03", f"afade=t=out:st={max(0, d - 0.03):.3f}:d=0.03",
                                          "apad", f"atrim=0:{d:.4f}") if x)
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s['in']:.3f}", "-t", f"{src_d + 0.15:.3f}", "-i", s["path"],
                     "-vn", "-af", af, str(ao)])
            else:
                run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{d:.4f}", str(ao)])
            vlist.append(vo.name)
            alist.append(ao.name)
            log(f"cut segment {i + 1}/{len(job['segments'])}: {s['src']} {s['in']:.2f}-{s['out']:.2f} -> {d:.2f}s")
        (work / "v.txt").write_text("".join(f"file '{v}'\n" for v in vlist))
        (work / "a.txt").write_text("".join(f"file '{a}'\n" for a in alist))
        a_all = work / "a_all.wav"
        anorm = [] if job.get("no_loudnorm") else ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "a.txt"), *anorm, "-ar", "48000", str(a_all)])
        out = Path(job["out"])
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "v.txt"), "-i", str(a_all),
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
             "-movflags", "+faststart", str(out)])
        return {"out": str(out), "segments": len(vlist), "graded_with": "numpy" if grade else "ffmpeg"}

    @staticmethod
    def _pipe(inp, vf, n, W, H, FPS, enc, vo, grade) -> None:
        import numpy as np
        dec = subprocess.Popen(["ffmpeg", "-v", "error", *inp, "-vf", vf + ",format=bgr24", "-frames:v", str(n),
                                "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        e = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                              "-r", str(FPS), "-i", "-", *enc, str(vo)], stdin=subprocess.PIPE)
        k, last, size = 0, None, W * H * 3
        while k < n:
            b = dec.stdout.read(size)
            if len(b) < size:
                break
            last = grade(np.frombuffer(b, np.uint8).reshape(H, W, 3)).tobytes()
            e.stdin.write(last)
            k += 1
        if last is None:
            dec.kill()
            e.stdin.close()
            e.wait()
            raise EngineFailed(f"no frames decoded for {vo.name}")
        while k < n:
            e.stdin.write(last)
            k += 1
        e.stdin.close()
        e.wait()
        dec.stdout.close()
        dec.wait()
        if e.returncode != 0:
            raise EngineFailed(f"encoder failed for {vo.name}")


ENGINES = [FfmpegCut]
