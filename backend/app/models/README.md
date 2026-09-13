# Fixed THRYV wake classifier — Beta

`thryv.json` is a single THRYV classifier, version 2: frozen speech embeddings followed by
a 64-unit ReLU layer and sigmoid output. Its threshold is fixed at 0.5. No user can rename
the keyword. Runtime uses ONNX feature extraction and NumPy; scikit-learn is training-only.

Training used 80 synthetic speakers from Piper's `en_US-libritts_r-medium`: 640 positive
clips, 1,920 negative speech clips and 320 noise clips. Another 20 speakers plus 80 noise clips
were held out for validation: 156/160 positives detected and 548/560 negatives rejected.
The independent Lessac invocation set passed 8/12 combined cases: three missed invocations
and one false activation on “Drive”. These numbers do not establish human/noisy-room accuracy.
The voice UI discloses this limitation and recommends Talk. Permissions remain authoritative.

Feature assets come from [openWakeWord v0.5.1](https://github.com/dscripka/openWakeWord/releases/tag/v0.5.1).
The [feature backbone](https://github.com/dscripka/openWakeWord#model-architecture) is described
upstream as Apache-2.0; this project trains its own classification head, not an upstream
pretrained wake-phrase head. Feature preprocessing follows openWakeWord's conventions
(David Scripka, Apache-2.0). Downloads are checksum-pinned in `scripts/setup_voice.py`.

Training voice: [Piper LibriTTS-R model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts_r/medium/MODEL_CARD),
which attributes [LibriTTS-R](https://www.openslr.org/141/) under CC BY 4.0 and notes fine-tuning
from Lessac. Retain upstream model/dataset terms. PocketSphinx's bundled acoustic assets
retain their upstream notices; it locates boundaries after classifier detection.

`scripts/train_fixed_wake.py` records the generation seed and speaker IDs. `--fit-head` reuses
cached features, holds out the last 20 speakers and fits the version-2 head with seed 4971.
Piper's stochastic synthesis means regenerated audio is not bit-for-bit reproducible.
Training audio/features are ignored local artifacts, never user microphone recordings.
No further wake training is part of the V2 Beta/V3 release run.
