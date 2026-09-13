"""One canonical THRYV invocation, with bounded conversational prefixes and ASR spellings."""

import re
import unicodedata

# 'thrive'/'thryve' are pronunciation spellings of THRYV, not configurable wake words.
# Require invocation position: mentioning THRYV later in unrelated speech cannot activate it.
INVOCATION = re.compile(
    r"^\s*(?:(?:hey|hi|hello|okay|ok|well|um|uh)[\s,!.]+){0,3}"
    r"(?:thryv|thrive|thryve)\b[\s,:;!?.—-]*(.*)$",
    re.I | re.S,
)


def transcribe_wake(recognizer, samples):
    # Vocabulary hints can turn unrelated speech (e.g. "drive") into THRYV.
    # Activation must depend on an unbiased transcription, never a suggested word.
    segments, _ = recognizer.transcribe(
        samples,
        language="en",
        beam_size=5,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        hotwords=None,
        initial_prompt=None,
        prefix=None,
    )
    return " ".join(
        s.text.strip() for s in segments if s.avg_logprob >= -0.9 and s.no_speech_prob < 0.7
    )[:8000]


def detect_wake(transcript: str):
    match = INVOCATION.match(unicodedata.normalize("NFKC", transcript))
    return {"detected": bool(match), "command": match.group(1).strip() if match else ""}
