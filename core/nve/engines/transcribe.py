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
from nve.util import log, retry_once, run

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
        if not ctx.env.get("node"):
            return False, "node >= 22 not found"
        if (ctx.env.get("network") or {}).get("huggingface.co") is False:
            return False, "whisper model download blocked (huggingface.co)"
        return True, ""

    def run(self, job: dict, ctx: Ctx) -> dict:
        from nve.env import npx
        node = ctx.env["node"]
        work = Path(job["work"])
        audio = extract_audio(Path(job["src"]), work / f"{Path(job['out']).stem}.wav")
        lang = job.get("language")
        model = "small.en" if lang in (None, "en") else "small"
        args = ["transcribe", str(audio.resolve()), "--json", "--model", model]
        if lang and lang != "en":
            args += ["--language", lang]
        retry_once(lambda: npx(node, args, timeout=1800, check=True), "whisper (npx hyperframes transcribe)",
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
        blocked, _ = self._model_source(ctx)
        if blocked:
            return False, blocked
        try:
            import faster_whisper  # noqa: F401
            return True, ""
        except ImportError:
            pass
        if os.environ.get("NVE_NO_PIP") == "1":
            return False, "faster-whisper not installed"
        return True, "not installed yet: pip-installed on first use"

    @staticmethod
    def _model_source(ctx: Ctx) -> tuple[str | None, bool]:
        """(why unavailable, may use nve-resources). The model comes from Hugging Face or, when the edition
        lists it in `resources` (newbie), from the nve-resources git repo (see nve.resources)."""
        from nve import resources
        net = ctx.env.get("network") or {}
        mirror = "whisper-small" in ((ctx.env.get("edition") or {}).get("resources") or [])
        if os.environ.get("NVE_WHISPER_MODEL") or resources.is_cached("whisper-small"):
            return None, mirror
        if net.get("huggingface.co") is False and not (mirror and net.get("github.com", True)):
            return "whisper model download blocked (huggingface.co)", mirror
        return None, mirror

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
        model = self._load_model(WhisperModel, ctx)
        # Decode ourselves (16 kHz mono float32): faster_whisper.decode_audio breaks with newer PyAV
        # ("open() got an unexpected keyword argument 'metadata_errors'").
        segs, info = model.transcribe(wav_float32(audio), language=lang, word_timestamps=True, vad_filter=False)
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


    def _load_model(self, WhisperModel, ctx: Ctx):
        from nve import resources
        load = lambda src: WhisperModel(src, device="cpu", compute_type="int8")  # noqa: E731
        _, mirror = self._model_source(ctx)
        name = os.environ.get("NVE_WHISPER_MODEL")
        if name:
            return load(name)
        if resources.is_cached("whisper-small"):
            return load(str(resources.cache_dir("whisper-small")))
        hf_blocked = (ctx.env.get("network") or {}).get("huggingface.co") is False
        if not hf_blocked:
            try:
                return retry_once(lambda: load("small"), "whisper model download (Hugging Face)")
            except Exception as e:  # noqa: BLE001
                if not mirror:
                    raise EngineUnavailable(f"model download failed twice ({str(e)[:120]}; {ALLOWLIST_HINT})") from e
                log(f"Hugging Face download failed ({str(e)[:80]}); using nve-resources on GitHub")
        if not mirror:
            raise EngineUnavailable("whisper model download blocked (huggingface.co)")
        try:
            d = resources.fetch("whisper-small")
        except NveError as e:
            raise EngineUnavailable(str(e)) from e
        os.environ["NVE_WHISPER_MODEL"] = str(d)
        return load(str(d))


def wav_float32(path: Path):
    """16-bit PCM WAV (as extract_audio writes it: mono 16 kHz) -> float32 numpy array in [-1, 1]."""
    import wave

    import numpy as np
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != 16000 or w.getnchannels() != 1:
            raise EngineFailed("expected 16 kHz mono 16-bit WAV")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


ENGINES = [Scribe, Whisper, FasterWhisper]
