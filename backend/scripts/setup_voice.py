"""Opt-in model download. Inference never downloads models or sends speech to these hosts."""

import hashlib
from pathlib import Path

import httpx
from faster_whisper.utils import download_model

root = Path(".models")
root.mkdir(exist_ok=True)
download_model("base.en", output_dir=str(root / "whisper-base.en"))
base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
with httpx.Client(timeout=60, follow_redirects=True) as client:
    for name in ["en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json", "MODEL_CARD"]:
        target = root / ("piper-MODEL_CARD" if name == "MODEL_CARD" else name)
        if target.exists():
            continue
        with client.stream("GET", base + name) as response:
            response.raise_for_status()
            with target.with_suffix(target.suffix + ".part").open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        target.with_suffix(target.suffix + ".part").replace(target)
    wake_root = root / "thryv-wake"
    wake_root.mkdir(exist_ok=True)
    for name, digest in {
        "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
        "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    }.items():
        target = wake_root / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        response = client.get(
            "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/" + name
        )
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != digest:
            raise ValueError("Wake feature model checksum mismatch")
        target.write_bytes(response.content)
print("Local speech models are ready. Read .models/piper-MODEL_CARD for voice licensing.")
