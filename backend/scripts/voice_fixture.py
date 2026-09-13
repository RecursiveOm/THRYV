"""Opt-in synthetic microphone fixture for live acceptance; never records a person."""

import asyncio
import io
import sys
import wave
from pathlib import Path

import numpy as np

from app.config import Settings
from app.speech import LocalSpeech


async def main():
    speech = LocalSpeech(Settings())
    phrase = "What system am I connected to?"
    if "--chrome" in sys.argv[2:]:
        phrase = "Open Chrome"
    if "--wake" in sys.argv[2:]:
        phrase = "Hey Thryv, what system am I connected to?"
    if "--wake-chrome" in sys.argv[2:]:
        phrase = "Hey Thryv, open Chrome"
    data = await speech.speak(phrase)
    with wave.open(io.BytesIO(data), "rb") as wav:
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    pcm = np.interp(
        np.arange(int(len(samples) * 16000 / rate)) * rate / 16000,
        np.arange(len(samples)),
        samples,
    ).astype("<i2")
    # Add silence so the browser can capture the complete utterance without looping it.
    pcm = np.concatenate((np.zeros(4000, dtype="<i2"), pcm, np.zeros(64000, dtype="<i2")))
    target = Path(sys.argv[1])
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm.tobytes())
    await asyncio.to_thread(target.chmod, 0o600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("Voice fixture could not be generated; raw errors withheld.")
        raise SystemExit(1) from None
