"""Guard the recognizer boundary, not just matching already-transcribed text."""

from types import SimpleNamespace

import pytest

from app.wake import detect_wake, transcribe_wake


@pytest.mark.parametrize(
    ("text", "detected", "command"),
    [
        ("Thryv", True, ""),
        ("Hey Thryv", True, ""),
        ("Hi Thryv", True, ""),
        ("Okay Thryv", True, ""),
        ("Hey Thryv, open Chrome", True, "open Chrome"),
        ("Drive", False, ""),
        ("Hey driver, open Chrome", False, ""),
        ("Pride", False, ""),
        ("I want to thrive in my career", False, ""),
    ],
)
def test_wake_recognition_cannot_be_coerced_by_vocabulary_guidance(text, detected, command):
    class Recognizer:
        def transcribe(self, samples, **options):
            assert samples is audio
            assert options["condition_on_previous_text"] is False
            # Simulate the observed failure: a suggested spelling overrides acoustics.
            guided = any(options.get(key) for key in ("hotwords", "initial_prompt", "prefix"))
            transcript = "Thryv" if guided else text
            return [SimpleNamespace(text=transcript, avg_logprob=-0.2, no_speech_prob=0.1)], None

    audio = object()
    result = detect_wake(transcribe_wake(Recognizer(), audio))
    assert result == {"detected": detected, "command": command}


@pytest.mark.parametrize("logprob,no_speech", [(-1.0, 0.1), (-0.2, 0.8)])
def test_uncertain_wake_transcription_is_rejected(logprob, no_speech):
    class Recognizer:
        def transcribe(self, samples, **options):
            return [
                SimpleNamespace(text="Thryv", avg_logprob=logprob, no_speech_prob=no_speech)
            ], None

    assert detect_wake(transcribe_wake(Recognizer(), object()))["detected"] is False


def test_wake_rejection_never_calls_general_transcription():
    np = pytest.importorskip("numpy")
    from app.wake_detector import wake_command

    detector = SimpleNamespace(locate=lambda pcm: None)

    def forbidden(pcm):
        pytest.fail("ASR must not authorize wake activation")

    assert wake_command(np.ones(32000, dtype=np.int16), detector, forbidden) == {
        "detected": False,
        "command": "",
    }


def test_acoustic_wake_preserves_complete_command_audio():
    np = pytest.importorskip("numpy")
    from app.wake_detector import wake_command

    pcm = np.full(48000, 2000, dtype=np.int16)
    pcm[:4000] = 0
    detector = SimpleNamespace(locate=lambda audio: (4000, 12000))

    def transcribe(tail):
        assert np.shares_memory(tail, pcm)
        assert np.array_equal(tail, pcm[12000:])
        return "open Chrome"

    assert wake_command(pcm, detector, transcribe) == {"detected": True, "command": "open Chrome"}


def test_keyword_only_does_not_transcribe_tail_silence():
    np = pytest.importorskip("numpy")
    from app.wake_detector import wake_command

    detector = SimpleNamespace(locate=lambda pcm: (4000, 12000))

    def forbidden(pcm):
        pytest.fail("Silence must not become a hallucinated command")

    assert wake_command(np.zeros(48000, dtype=np.int16), detector, forbidden) == {
        "detected": True,
        "command": "",
    }


def test_background_mention_is_rejected_after_acoustic_detection():
    np = pytest.importorskip("numpy")
    from app.wake_detector import wake_command

    pcm = np.full(48000, 2000, dtype=np.int16)
    detector = SimpleNamespace(locate=lambda audio: (12000, 20000))
    calls = []

    def transcribe(prefix):
        calls.append(len(prefix))
        return "I want to"

    assert wake_command(pcm, detector, transcribe) == {"detected": False, "command": ""}
    assert calls == [12000]


def test_missing_wake_assets_do_not_disable_talk(tmp_path, monkeypatch):
    import app.speech as speech
    from app.config import Settings

    (tmp_path / "embedding_model.onnx").touch()
    tts = tmp_path / "tts.onnx"
    tts.touch()
    monkeypatch.setattr(speech.importlib.util, "find_spec", lambda name: object())
    runtime = speech.LocalSpeech(
        Settings(
            stt_model_path=str(tmp_path), wake_model_path=str(tmp_path), tts_model_path=str(tts)
        )
    )
    assert runtime.status()["wake"] is False
    assert runtime.status()["stt"] is True
    assert runtime.status()["tts"] is True
    (tmp_path / "melspectrogram.onnx").touch()
    assert runtime.status()["wake"] is True
