"""transcribe socket: word-level transcript in Scribe shape
{"engine", "language_code", "words": [{"type": "word"|"spacing", "text", "start", "end"}]}."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from nve.engines import Ctx, Engine, EngineFailed, EngineUnavailable
from nve.env import HYPERFRAMES_VERSION, get_key
from nve.paths import NveError
from nve.util import retry_once, run

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ALLOWLIST_HINT = ("on claude.ai, add api.elevenlabs.io, huggingface.co, *.huggingface.co, *.hf.co to "
                  "Settings > Capabilities > Additional allowed domains (web or desktop app)")


def extract_audio(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])
    return dst


def _multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n'.encode() + file_path.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


class Scribe(Engine):
    id, capability = "scribe", "transcribe"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        return (True, "") if get_key("ELEVENLABS_API_KEY", ctx.workspace) else (False, "no ELEVENLABS_API_KEY")

    def run(self, job: dict, ctx: Ctx) -> dict:
        key = get_key("ELEVENLABS_API_KEY", ctx.workspace)
        audio = extract_audio(Path(job["src"]), Path(job["work"]) / f"{Path(job['out']).stem}.wav")
        fields = {"model_id": "scribe_v1", "diarize": "true", "tag_audio_events": "true", "timestamps_granularity": "word"}
        if job.get("language"):
            fields["language_code"] = job["language"]
        body, ctype = _multipart(fields, "file", audio)
        req = urllib.request.Request(SCRIBE_URL, data=body, method="POST",
                                     headers={"xi-api-key": key, "Content-Type": ctype})

        def call():
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code >= 500 or e.code == 429:
                    raise  # server-side: worth the one retry
                raise EngineFailed(f"Scribe HTTP {e.code}: {e.read()[:300].decode(errors='ignore')}") from e

        try:
            data = retry_once(call, "Scribe request", on=(OSError,))  # URLError/HTTPError 5xx; not EngineFailed
        except EngineFailed:
            raise
        except urllib.error.HTTPError as e:
            raise EngineFailed(f"Scribe HTTP {e.code} (after one retry)") from e
        except (urllib.error.URLError, OSError) as e:
            raise EngineUnavailable(f"network: {getattr(e, 'reason', e)} (after one retry; {ALLOWLIST_HINT})") from e
        data["engine"] = "scribe"
        Path(job["out"]).write_text(json.dumps(data, ensure_ascii=False, indent=1))
        return {"out": job["out"], "words": sum(1 for w in data.get("words", []) if w.get("type") == "word")}


class Whisper(Engine):
    """Offline whisper.cpp through the HyperFrames CLI. Weaker on Vietnamese fillers than Scribe."""
    id, capability = "whisper", "transcribe"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        return (True, "") if ctx.env.get("node") else (False, "node >= 22 not found")

    def run(self, job: dict, ctx: Ctx) -> dict:
        node = ctx.env["node"]
        work = Path(job["work"])
        audio = extract_audio(Path(job["src"]), work / f"{Path(job['out']).stem}.wav")
        lang = job.get("language")
        model = "small.en" if lang in (None, "en") else "small"
        cmd = ["npx", "-y", f"hyperframes@{HYPERFRAMES_VERSION}", "transcribe", str(audio), "--json", "--model", model]
        if lang and lang != "en":
            cmd += ["--language", lang]
        env = {**os.environ, "PATH": node["bin_dir"] + os.pathsep + os.environ.get("PATH", "")}
        retry_once(lambda: run(cmd, env=env, timeout=1800), "whisper (npx hyperframes transcribe)",
                   on=(NveError,))  # failed command; a 30-min timeout is not retried
        tj = audio.parent / "transcript.json"
        if not tj.exists():
            raise EngineFailed("whisper produced no transcript.json")
        raw = json.loads(tj.read_text())
        words = raw if isinstance(raw, list) else raw.get("words", [])
        out, prev = [], None
        for w in words:
            text = (w.get("text") or "").strip()
            if not text or w.get("start") is None or w.get("end") is None:
                continue
            if prev is not None and w["start"] > prev:
                out.append({"type": "spacing", "text": " ", "start": prev, "end": w["start"]})
            out.append({"type": "word", "text": text, "start": w["start"], "end": w["end"]})
            prev = w["end"]
        tj.unlink()
        Path(job["out"]).write_text(json.dumps({"engine": "whisper", "language_code": lang, "words": out},
                                               ensure_ascii=False, indent=1))
        return {"out": job["out"], "words": sum(1 for x in out if x["type"] == "word")}


class FasterWhisper(Engine):
    """Pure-Python whisper (CTranslate2). For sandboxes without Node (claude.ai): installed from PyPI on
    first use; the model is downloaded from Hugging Face, which some sandboxes block."""
    id, capability = "faster-whisper", "transcribe"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        # Only a check: never installs here (`nve engines` / doctor must not change the venv).
        try:
            import faster_whisper  # noqa: F401
            return True, ""
        except ImportError:
            pass
        if os.environ.get("NVE_NO_PIP") == "1":
            return False, "faster-whisper not installed"
        return True, "not installed yet: pip-installed on first use"

    @staticmethod
    def _install() -> None:
        import subprocess as sp
        import sys

        def pip_install():
            r = sp.run([sys.executable, "-m", "pip", "install", "--quiet", "faster-whisper"], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout or "pip failed").strip()[-300:])

        try:
            retry_once(pip_install, "pip install faster-whisper")
        except RuntimeError as e:
            raise EngineUnavailable(f"pip install faster-whisper failed twice: {str(e).splitlines()[-1][:160]}") from e

    def run(self, job: dict, ctx: Ctx) -> dict:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self._install()
            import importlib
            importlib.invalidate_caches()
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise EngineUnavailable("faster-whisper import failed after install") from e
        audio = extract_audio(Path(job["src"]), Path(job["work"]) / f"{Path(job['out']).stem}.wav")
        lang = job.get("language")
        name = os.environ.get("NVE_WHISPER_MODEL", "small")
        try:
            model = retry_once(lambda: WhisperModel(name, device="cpu", compute_type="int8"),
                               "whisper model download (Hugging Face)")
        except Exception as e:
            raise EngineUnavailable(f"model download failed twice ({str(e)[:120]}; {ALLOWLIST_HINT})") from e
        segs, info = model.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=False)
        out, prev = [], None
        for seg in segs:
            for w in seg.words or []:
                text = (w.word or "").strip()
                if not text:
                    continue
                if prev is not None and w.start > prev:
                    out.append({"type": "spacing", "text": " ", "start": round(prev, 3), "end": round(w.start, 3)})
                out.append({"type": "word", "text": text, "start": round(w.start, 3), "end": round(w.end, 3)})
                prev = w.end
        Path(job["out"]).write_text(json.dumps({"engine": "faster-whisper", "language_code": lang or info.language,
                                                "words": out}, ensure_ascii=False, indent=1))
        return {"out": job["out"], "words": sum(1 for x in out if x["type"] == "word")}


ENGINES = [Scribe, Whisper, FasterWhisper]
