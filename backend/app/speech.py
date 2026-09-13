"""Local speech adapters run in bounded, killable workers without server credentials."""

import asyncio
import importlib.util
import io
import json
import os
import sys
import wave
from pathlib import Path

from app.errors import AppError

MAX_AUDIO_BYTES = 960_044


def validate_audio(data):
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16000
                or audio.getcomptype() != "NONE"
                or not 1600 <= audio.getnframes() <= 480000
            ):
                raise ValueError()
            samples = audio.readframes(480001)
            if len(samples) != audio.getnframes() * 2:
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise AppError(
            "invalid_audio", "Record 0.1–30 seconds of mono speech, then try again.", 422
        ) from None


class LocalSpeech:
    def __init__(self, settings):
        self.stt_path = Path(settings.stt_model_path).resolve()
        self.wake_path = Path(settings.wake_model_path).resolve()
        self.tts_path = Path(settings.tts_model_path).resolve()
        self.busy = False
        self.lock = asyncio.Lock()
        self.worker_directory = str(Path(__file__).resolve().parents[1])

    def status(self):
        stt = self.stt_path.is_dir() and importlib.util.find_spec("faster_whisper") is not None
        tts = self.tts_path.is_file() and importlib.util.find_spec("piper") is not None
        return {
            "stt": stt,
            "tts": tts,
            "wake": stt
            and all(
                (self.wake_path / name).is_file()
                for name in ("embedding_model.onnx", "melspectrogram.onnx")
            )
            and importlib.util.find_spec("pocketsphinx") is not None,
            "local": True,
            "max_seconds": 30,
        }

    async def _run(self, mode, data):
        if not self.status()[mode]:
            raise AppError(
                "voice_unavailable", "Local speech is not configured. Text chat is available.", 503
            )
        try:
            # Allow an aborted worker to finish cleanup before its replacement starts.
            async with asyncio.timeout(2):
                await self.lock.acquire()
        except TimeoutError:
            raise AppError(
                "voice_busy", "Speech is busy. Try again shortly or use text.", 429
            ) from None
        self.busy = True
        process = None
        try:
            model = {"stt": self.stt_path, "tts": self.tts_path, "wake": self.wake_path}[mode]
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.speech_worker",
                mode,
                str(model),
                *([str(self.stt_path)] if mode == "wake" else []),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={
                    "PATH": os.defpath,
                    "LANG": "C.UTF-8",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "OMP_NUM_THREADS": "2",
                },
                cwd=self.worker_directory,
            )
            async with asyncio.timeout(50):
                output, _ = await process.communicate(data)
            if process.returncode or len(output) > 6_000_000:
                raise AppError(
                    "voice_failed", "Speech could not finish. Please use text or try again.", 502
                )
            return output
        except TimeoutError:
            raise AppError(
                "voice_timeout", "Speech timed out. Please use text or try again.", 504
            ) from None
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            self.busy = False
            self.lock.release()

    async def transcribe(self, data):
        validate_audio(data)
        output = await self._run("stt", data)
        try:
            text = json.loads(output)["text"].strip()
            if not isinstance(text, str) or not 1 <= len(text) <= 8000:
                raise ValueError()
        except (KeyError, ValueError, TypeError, AttributeError):
            raise AppError(
                "no_speech", "No clear speech was detected. Try again or type your message.", 422
            ) from None
        return text

    async def speak(self, text):
        return await self._run("tts", text.encode())

    async def wake(self, data):
        validate_audio(data)
        output = await self._run("wake", data)
        try:
            result = json.loads(output)
            if (
                type(result.get("detected")) is not bool
                or not isinstance(result.get("command"), str)
                or len(result["command"]) > 8000
                or (not result["detected"] and result["command"])
            ):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AppError("voice_failed", "Wake recognition could not finish.", 502) from None
        return result
