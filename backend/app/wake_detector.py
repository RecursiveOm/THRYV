"""Fixed THRYV acoustic classifier using openWakeWord's local ONNX feature models.

The classifier authorizes activation. PocketSphinx only locates its keyword boundary;
neither a transcript nor a keyword-spotter hypothesis can authorize activation alone.
"""

import json
import re
from pathlib import Path


class WakeDetector:
    def __init__(self, directory, *, classifier=None):
        import numpy as np
        import onnxruntime as ort

        directory = Path(directory)
        model = json.loads(
            (
                Path(classifier) if classifier else Path(__file__).parent / "models/thryv.json"
            ).read_text()
        )
        if model["keyword"] != "THRYV" or model["version"] not in {1, 2}:
            raise ValueError("Invalid wake model")
        self.version = model["version"]
        if self.version == 1:
            self.weights = np.asarray(model["weights"], dtype=np.float32)
            self.bias = model["bias"]
        else:
            self.mean = np.asarray(model["mean"], dtype=np.float32)
            self.scale = np.asarray(model["scale"], dtype=np.float32)
            self.layers = [
                (
                    np.asarray(layer["weights"], dtype=np.float32),
                    np.asarray(layer["bias"], dtype=np.float32),
                )
                for layer in model["layers"]
            ]
        self.threshold = model["threshold"]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.mel = ort.InferenceSession(
            str(directory / "melspectrogram.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.embedding = ort.InferenceSession(
            str(directory / "embedding_model.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def features(self, pcm):
        import numpy as np

        # openWakeWord feature convention: 76 mel frames per embedding, stride 8.
        mel = self.mel.run(None, {"input": pcm[None, :].astype(np.float32)})[0].squeeze()
        mel = mel / 10 + 2
        windows = np.stack([mel[i : i + 76] for i in range(0, len(mel) - 75, 8)])
        return self.embedding.run(None, {"input_1": windows[..., None].astype(np.float32)})[
            0
        ].flatten()

    def locate(self, pcm):
        import numpy as np

        # Identical fixed windows to training; pad to include short standalone invocations.
        padded = np.concatenate(
            (np.zeros(8000, dtype=np.int16), pcm, np.zeros(32000, dtype=np.int16))
        )
        hits = []
        for start in range(0, len(padded) - 32000 + 1, 2560):
            score = self.score(padded[start : start + 32000])
            if score >= self.threshold:
                hits.append((max(0, start - 8000), start + 32000 - 8000))
        if not hits:
            return None

        from pocketsphinx import Decoder

        # One pronunciation, TH R AY V; no custom dictionary or alternative wake keywords.
        decoder = Decoder(keyphrase="thrive", kws_threshold=1e-15, loglevel="FATAL")
        decoder.start_utt()
        decoder.process_raw(pcm.tobytes(), False, True)
        decoder.end_utt()
        if not decoder.hyp():
            return None
        candidates = [
            (segment.prob, segment.start_frame * 160, (segment.end_frame + 1) * 160)
            for segment in decoder.seg()
            if segment.word == "thrive"
            and segment.start_frame <= 175
            and any(
                left <= segment.start_frame * 160 and (segment.end_frame + 1) * 160 <= right
                for left, right in hits
            )
        ]
        if not candidates:
            return None
        _, start, end = max(candidates)
        return start, end

    def score(self, pcm):
        import numpy as np

        x = self.features(pcm)
        if self.version == 1:
            logit = float(np.dot(x, self.weights)) + self.bias
        else:
            x = (x - self.mean) / self.scale
            for weights, bias in self.layers[:-1]:
                x = np.maximum(0, x @ weights + bias)
            weights, bias = self.layers[-1]
            logit = float((x @ weights + bias)[0])
        return float(1 / (1 + np.exp(-np.clip(logit, -60, 60))))


def wake_command(pcm, detector, transcribe):
    """Keep buffered post-keyword speech; ASR cannot create an activation."""
    import numpy as np

    boundary = detector.locate(pcm)
    if boundary is None:
        return {"detected": False, "command": ""}
    start, end = boundary
    prefix = pcm[:start]
    prefix_frames = len(prefix) // 320
    if prefix_frames:
        energy = np.sqrt(
            np.mean((prefix[: prefix_frames * 320].reshape(-1, 320) / 32768) ** 2, axis=1)
        )
        if np.count_nonzero(energy > 0.008) >= 10:
            # ASR may reject a background mention, but it cannot supply the keyword.
            words = re.findall(r"[a-z]+", transcribe(prefix).casefold())
            if not 1 <= len(words) <= 3 or any(
                word not in {"hey", "hi", "hello", "okay", "ok", "well", "um", "uh"}
                for word in words
            ):
                return {"detected": False, "command": ""}
    tail = pcm[end:]
    # Avoid transcribing pure tail silence/breath into a hallucinated command.
    frames = len(tail) // 320
    if not frames:
        return {"detected": True, "command": ""}
    energy = np.sqrt(np.mean((tail[: frames * 320].reshape(-1, 320) / 32768) ** 2, axis=1))
    if np.count_nonzero(energy > 0.008) < 10:
        return {"detected": True, "command": ""}
    return {"detected": True, "command": transcribe(tail)}
