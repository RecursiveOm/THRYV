"""Opt-in real local speech/wake recognition check using synthetic invocation examples."""

import argparse
import asyncio
import io
import wave
from pathlib import Path

import numpy as np

from app.config import Settings
from app.errors import AppError
from app.speech import LocalSpeech


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, choices=range(1, 13), help="Run one numbered sample")
    parser.add_argument(
        "--fixtures", type=Path, help="Cache/reuse synthetic WAVs for repeatable checks"
    )
    args = parser.parse_args()
    speech = LocalSpeech(Settings())
    examples = [
        ("Thryv", True, ""),
        ("Hey Thryv", True, ""),
        ("Hi Thryv", True, ""),
        ("Okay Thryv", True, ""),
        ("Hey Thryv, open Chrome", True, "open chrome"),
        ("Thryv, what system am I connected to?", True, "what system am i connected to"),
        ("Pride", False, ""),
        ("Drive", False, ""),
        ("Hey driver, open Chrome", False, ""),
        ("I want to thrive in my career", False, ""),
        ("The news is on television", False, ""),
        ("Open Chrome", False, ""),
    ]
    failures = 0
    for index, (phrase, detected, command) in enumerate(examples, 1):
        if args.sample is not None and index != args.sample:
            continue
        cached = args.fixtures / f"sample-{index}.wav" if args.fixtures else None
        if cached and cached.exists():
            wav_data = cached.read_bytes()
        else:
            wav_data = await synthesize(speech, phrase)
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(wav_data)
        try:
            result = await speech.wake(wav_data)
        except AppError as error:
            if error.code != "no_speech":
                raise
            result = {"detected": False, "command": ""}
        normalized = result["command"].strip().rstrip(".!?").casefold()
        if result["detected"] != detected or normalized != command:
            reason = "activation" if result["detected"] != detected else "command capture"
            print(f"FAIL local invocation sample {index}: {reason}; raw speech withheld")
            failures += 1
        else:
            print(f"PASS local invocation sample {index}")
    count = 1 if args.sample else len(examples)
    print(f"Local invocation checks: {count - failures} passed, {failures} failed")
    return int(bool(failures))


async def synthesize(speech, phrase):
    audio = await speech.speak(phrase)
    with wave.open(io.BytesIO(audio), "rb") as wav:
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    pcm = np.interp(
        np.arange(int(len(samples) * 16000 / rate)) * rate / 16000,
        np.arange(len(samples)),
        samples,
    ).astype("<i2")
    pcm = np.concatenate((np.zeros(4000, dtype="<i2"), pcm, np.zeros(24000, dtype="<i2")))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        print("FAIL local speech check; raw errors withheld")
        raise SystemExit(1) from None
