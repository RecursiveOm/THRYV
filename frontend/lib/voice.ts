import { ApiError } from "./api";
import { VoiceActivity } from "./voice-activity";
export type WakeResult = { detected: boolean; command: string };
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function wavFromSamples(
  chunks: Float32Array[],
  sourceRate: number,
): Blob {
  const count = chunks.reduce((n, part) => n + part.length, 0);
  const all = new Float32Array(count);
  let offset = 0;
  for (const part of chunks) {
    all.set(part, offset);
    offset += part.length;
  }
  const frames = Math.min(480000, Math.floor((count * 16000) / sourceRate));
  const buffer = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(buffer);
  const tag = (start: number, value: string) => {
    for (let i = 0; i < value.length; i++)
      view.setUint8(start + i, value.charCodeAt(i));
  };
  tag(0, "RIFF");
  view.setUint32(4, 36 + frames * 2, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  tag(36, "data");
  view.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++) {
    const start = Math.floor((i * sourceRate) / 16000);
    const end = Math.min(
      count,
      Math.max(start + 1, Math.floor(((i + 1) * sourceRate) / 16000)),
    );
    let sample = 0;
    for (let j = start; j < end; j++) sample += all[j];
    sample = Math.max(-1, Math.min(1, sample / (end - start)));
    view.setInt16(44 + i * 2, sample * (sample < 0 ? 32768 : 32767), true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export class VoiceCapture {
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private chunks: Float32Array[] = [];
  private stopped = false;
  private samples = 0;
  private vad = new VoiceActivity();
  private endSignalled = false;
  constructor(private onSpeechEnd?: () => void) {}
  get heardSpeech() {
    return this.vad.heardSpeech;
  }
  async start() {
    if (!navigator.mediaDevices?.getUserMedia)
      throw new Error(
        "Microphone access requires HTTPS or localhost. You can still type.",
      );
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    if (this.stopped) {
      this.close();
      return false;
    }
    this.context = new AudioContext();
    await this.context.audioWorklet.addModule("/audio-capture.js");
    if (this.stopped) {
      this.close();
      return false;
    }
    this.node = new AudioWorkletNode(this.context, "thryv-capture");
    const rate = this.context.sampleRate;
    this.node.port.onmessage = (event) => {
      if (!this.stopped && this.samples < rate * 30) {
        const data = (event.data as Float32Array).slice(
          0,
          rate * 30 - this.samples,
        );
        this.chunks.push(data);
        this.samples += data.length;
        const ended = this.vad.push(data, rate);
        // Keep only a short pre-roll while waiting, preserving the start of an invocation.
        while (
          !this.vad.started &&
          this.samples > rate * 0.4 &&
          this.chunks.length > 1
        ) {
          this.samples -= this.chunks.shift()!.length;
        }
        if (ended && !this.endSignalled) {
          this.endSignalled = true;
          this.onSpeechEnd?.();
        }
      }
    };
    const source = this.context.createMediaStreamSource(this.stream);
    const mute = this.context.createGain();
    mute.gain.value = 0;
    source.connect(this.node);
    this.node.connect(mute);
    mute.connect(this.context.destination);
    await this.context.resume();
    return true;
  }
  finish() {
    const rate = this.context?.sampleRate || 48000;
    this.close();
    const blob = wavFromSamples(this.chunks, rate);
    this.chunks = [];
    return blob;
  }
  cancel() {
    this.close();
    this.chunks = [];
  }
  private close() {
    this.stopped = true;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.node?.disconnect();
    void this.context?.close().catch(() => {});
  }
}

export async function voiceRequest(
  path: "transcribe" | "speak" | "wake",
  body: Blob | { text: string },
  signal: AbortSignal,
) {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/voice/${path}`, {
      method: "POST",
      headers: {
        "X-THRYV-Request": "1",
        "Content-Type": body instanceof Blob ? "audio/wav" : "application/json",
      },
      body: body instanceof Blob ? body : JSON.stringify(body),
      credentials: "include",
      redirect: "error",
      referrerPolicy: "no-referrer",
      cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(55000)]),
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("Speech could not reach the server. You can still type.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const messages: Record<string, string> = {
      voice_unavailable:
        "Local speech is not configured on this host. You can still type.",
      voice_busy: "Speech is busy. Try again shortly or type your message.",
      no_speech:
        "No clear speech was detected. Try again or type your message.",
      invalid_audio: "Record up to 30 seconds, then try again.",
      unauthenticated: "Sign in before using speech.",
    };
    const code = payload?.error?.code || "voice_failed";
    throw new ApiError(
      code,
      messages[code] || "Speech could not finish. You can still type.",
    );
  }
  if (path === "wake") {
    const data = await response.json();
    if (
      typeof data.detected !== "boolean" ||
      typeof data.command !== "string" ||
      data.command.length > 8000
    )
      throw new Error("Wake recognition could not finish. Use Talk or type.");
    return data as WakeResult;
  }
  if (path === "transcribe") {
    const data = await response.json();
    if (
      typeof data.text !== "string" ||
      !data.text.trim() ||
      data.text.length > 8000
    )
      throw new Error("No clear speech was detected.");
    return data.text as string;
  }
  return await response.blob();
}
