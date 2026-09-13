// Local energy-based VAD: require sustained sound, then 1.3 seconds of silence.
// A conservative noise floor avoids treating isolated clicks as complete utterances.
export class VoiceActivity {
  private noise = 0.002;
  private voicedMs = 0;
  private silenceMs = 0;
  started = false;
  heardSpeech = false;
  push(samples: Float32Array, rate: number): boolean {
    if (!samples.length || rate <= 0) return false;
    const rms = Math.sqrt(
      samples.reduce((sum, sample) => sum + sample * sample, 0) /
        samples.length,
    );
    const milliseconds = (samples.length * 1000) / rate;
    const voiced = rms >= Math.max(0.008, this.noise * 3);
    if (voiced) {
      this.started = true;
      this.voicedMs += milliseconds;
      this.silenceMs = 0;
      this.heardSpeech = this.voicedMs >= 240;
    } else {
      this.silenceMs += milliseconds;
      if (!this.started)
        this.noise = this.noise * 0.98 + Math.min(rms, 0.004) * 0.02;
      if (!this.heardSpeech && this.silenceMs >= 300) {
        this.started = false;
        this.voicedMs = 0;
      }
    }
    return this.heardSpeech && this.silenceMs >= 1300;
  }
}

// One active voice owner per browser origin, including while awaiting STT/tools/TTS.
export async function acquireVoiceLease(): Promise<() => void> {
  if (!navigator.locks)
    throw new Error(
      "This browser cannot coordinate microphone access. Try a current browser.",
    );
  return new Promise((resolve, reject) => {
    void navigator.locks
      .request("thryv-voice", { ifAvailable: true }, (lock) => {
        if (!lock) {
          reject(
            new Error(
              "Voice is active in another THRYV tab. Stop it there first.",
            ),
          );
          return;
        }
        return new Promise<void>((release) => resolve(release));
      })
      .catch(reject);
  });
}
