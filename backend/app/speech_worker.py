"""Internal fixed speech worker; not a general execution or user-command interface."""

import contextlib
import io
import json
import re
import sys
import wave

from app.wake import transcribe_wake
from app.wake_detector import WakeDetector, wake_command


def main():
    mode, model, *extra = sys.argv[1:]
    payload = sys.stdin.buffer.read(960_045)
    with contextlib.redirect_stdout(sys.stderr):
        if mode in {"stt", "wake"}:
            import numpy as np
            from faster_whisper import WhisperModel

            with wave.open(io.BytesIO(payload), "rb") as audio:
                samples = (
                    np.frombuffer(audio.readframes(480000), dtype="<i2").astype(np.float32) / 32768
                )
            if mode == "wake":
                command_recognizer = None

                def transcribe_command(tail):
                    nonlocal command_recognizer
                    if command_recognizer is None:
                        command_recognizer = WhisperModel(
                            extra[0],
                            device="cpu",
                            compute_type="int8",
                            cpu_threads=2,
                            num_workers=1,
                            local_files_only=True,
                        )
                    return transcribe_wake(command_recognizer, tail.astype(np.float32) / 32768)

                result = json.dumps(
                    wake_command(
                        (samples * 32768).astype("<i2"), WakeDetector(model), transcribe_command
                    )
                ).encode()
            elif not len(samples) or float(np.sqrt(np.mean(samples**2))) < 0.003:
                result = b'{"text":""}'
            else:
                recognizer = WhisperModel(
                    model,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=2,
                    num_workers=1,
                    local_files_only=True,
                )
                segments, _ = recognizer.transcribe(
                    samples,
                    language="en",
                    beam_size=3,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                )
                text = " ".join(s.text.strip() for s in segments)[:8000]
                result = json.dumps({"text": text}).encode()
        elif mode == "tts":
            from piper import PiperVoice

            output = io.BytesIO()
            voice = PiperVoice.load(model)
            with wave.open(output, "wb") as wav:
                # Speak the brand naturally; keep the canonical display/wake keyword THRYV.
                text = re.sub(r"\bthryv\b", "Thrive", payload.decode("utf8")[:600], flags=re.I)
                voice.synthesize_wav(text, wav)
            result = output.getvalue()
        else:
            raise ValueError("Unsupported worker")
    sys.stdout.buffer.write(result)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Speech and exception content must never reach application logs.
        raise SystemExit(1) from None
