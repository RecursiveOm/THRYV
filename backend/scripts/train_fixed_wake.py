"""Opt-in, local-only THRYV classifier training; never reads microphone or user audio.

Requires scikit-learn in the development environment and the separate Piper LibriTTS-R
training voice in .models/wake-training. The output is a candidate, not a runtime install.
"""

import argparse
import io
import json
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort
from piper import PiperVoice, SynthesisConfig
from piper.config import PiperConfig
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.wake_detector import WakeDetector

NEGATIVES = [
    "drive",
    "pride",
    "driver",
    "try",
    "tried",
    "five",
    "through",
    "free",
    "fry",
    "tribe",
    "alive",
    "strive",
    "strife",
    "thrice",
    "three",
    "private",
    "privacy",
    "describe",
    "arrive",
    "derive",
    "throat",
    "throw",
    "thrift",
    "bright",
    "dried",
    "dry",
    "prime",
    "fries",
    "price",
    "prize",
    "ride",
    "right",
    "fried",
    "thirty",
    "thrill",
    "threat",
    "open Chrome",
    "what system am I connected to",
    "the news is on television",
    "turn on the light",
    "hello there",
    "please stop",
    "thank you",
    "good morning",
    "the weather is nice",
    "I need a ride",
    "set a timer",
    "play some music",
    "hello computer",
    "this is a test",
    "how are you",
    "nothing to do",
    "we should take a drive",
    "I am proud of you",
    "the driver is outside",
    "please open the browser",
    "the train is arriving",
    "read the next page",
    "can you hear me",
    "okay fine",
    "hi friend",
    "hey Brian",
    "we have arrived",
    "close the window",
    "please wait",
    "that is right",
    "I want a private room",
    "the price is high",
    "this is the third time",
    "try again",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fit-head", action="store_true", help="Reuse cached features; no synthesis"
    )
    args = parser.parse_args()
    root = Path(".models/wake-training")
    if args.fit_head:
        fit_head(root)
        return
    rng = np.random.default_rng(614207)
    features = WakeDetector(".models/thryv-wake")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    voice = PiperVoice(
        session=ort.InferenceSession(
            str(root / "en_US-libritts_r-medium.onnx"), options, providers=["CPUExecutionProvider"]
        ),
        config=PiperConfig.from_dict(
            json.loads((root / "en_US-libritts_r-medium.onnx.json").read_text())
        ),
    )
    x, y = [], []
    speakers = rng.choice(904, 100, replace=False)
    for number, speaker in enumerate(speakers):
        for i in range(32):
            positive = i < 8
            word = "Thrive" if positive else str(rng.choice(NEGATIVES))
            prefix = str(rng.choice(["", "Hey ", "Hi ", "Okay ", "Hello ", "Well ", "Um "]))
            phrase = prefix + word + str(rng.choice(["", ".", "!"]))
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                voice.synthesize_wav(
                    phrase,
                    wav,
                    syn_config=SynthesisConfig(
                        speaker_id=int(speaker), length_scale=float(rng.uniform(0.85, 1.15))
                    ),
                )
            with wave.open(io.BytesIO(output.getvalue())) as wav:
                rate = wav.getframerate()
                pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
            pcm = np.interp(
                np.arange(int(len(pcm) * 16000 / rate)) * rate / 16000,
                np.arange(len(pcm)),
                pcm,
            )
            # Vary the keyword end position without truncating its final phones.
            tail = int(rng.uniform(0.1, 0.7) * 16000)
            pcm = np.concatenate((np.zeros(32000), pcm, np.zeros(tail)))[-32000:]
            pcm = pcm * rng.uniform(0.4, 1.2) + rng.normal(0, rng.uniform(0, 100), 32000)
            x.append(features.features(np.clip(pcm, -32768, 32767).astype(np.int16)))
            y.append(int(positive))
        if (number + 1) % 10 == 0:
            print(f"Generated {number + 1}/100 synthetic training speakers", flush=True)
    for i in range(400):
        pcm = rng.normal(0, rng.uniform(0, 2000), 32000)
        if i % 2:
            pcm += np.sin(
                np.arange(32000) / 16000 * 2 * np.pi * rng.uniform(50, 1600)
            ) * rng.uniform(0, 1500)
        x.append(features.features(np.clip(pcm, -32768, 32767).astype(np.int16)))
        y.append(0)
    np.savez_compressed(root / "training-features.npz", x=np.asarray(x), y=np.asarray(y))
    classifier = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.01, max_iter=500, class_weight={0: 2, 1: 1})
    )
    classifier.fit(x, y)
    scale, head = classifier.steps[0][1], classifier.steps[1][1]
    weights = head.coef_[0] / scale.scale_
    model = {
        "version": 1,
        "keyword": "THRYV",
        "sample_rate": 16000,
        "window_samples": 32000,
        "step_samples": 2560,
        "threshold": 0.5,
        "weights": weights.tolist(),
        "bias": float(head.intercept_[0] - np.dot(weights, scale.mean_)),
    }
    (root / "candidate.json").write_text(json.dumps(model, separators=(",", ":")) + "\n")
    (root / "training-manifest.json").write_text(
        json.dumps(
            {
                "seed": 614207,
                "speakers": speakers.tolist(),
                "examples": len(y),
                "positives": int(sum(y)),
                "threshold": 0.5,
            },
            indent=2,
        )
        + "\n"
    )
    print("Candidate trained; run held-out positive/negative acceptance before installing it.")


def fit_head(root):
    data = np.load(root / "training-features.npz")
    x, y = data["x"], data["y"]
    train = np.r_[np.arange(80 * 32), np.arange(3200, 3520)]
    validation = np.r_[np.arange(80 * 32, 3200), np.arange(3520, 3600)]
    scale = StandardScaler().fit(x[train])
    head = MLPClassifier(
        hidden_layer_sizes=(64,),
        alpha=0.01,
        max_iter=100,
        batch_size=128,
        random_state=4971,
        early_stopping=False,
    )
    head.fit(scale.transform(x[train]), y[train])
    predicted = head.predict(scale.transform(x[validation]))
    actual = y[validation]
    report = {
        "positive_passed": int(sum(predicted[actual == 1] == 1)),
        "positive_total": int(sum(actual == 1)),
        "negative_passed": int(sum(predicted[actual == 0] == 0)),
        "negative_total": int(sum(actual == 0)),
    }
    model = {
        "version": 2,
        "keyword": "THRYV",
        "sample_rate": 16000,
        "window_samples": 32000,
        "step_samples": 2560,
        "threshold": 0.5,
        "mean": scale.mean_.tolist(),
        "scale": scale.scale_.tolist(),
        "layers": [
            {"weights": weights.tolist(), "bias": bias.tolist()}
            for weights, bias in zip(head.coefs_, head.intercepts_, strict=True)
        ],
    }
    (root / "candidate-mlp.json").write_text(json.dumps(model, separators=(",", ":")) + "\n")
    (root / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
