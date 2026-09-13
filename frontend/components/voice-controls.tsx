"use client";
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";
import { Mic, Square, Volume2 } from "lucide-react";
import { accountRequest } from "@/lib/api";
import { VoiceCapture, voiceRequest, type WakeResult } from "@/lib/voice";
import { acquireVoiceLease } from "@/lib/voice-activity";

export function VoiceControls({
  onTranscript,
  reply,
  busy,
  waitingForDevice,
}: {
  onTranscript: (text: string) => Promise<void>;
  reply: string;
  busy: boolean;
  waitingForDevice: boolean;
}) {
  const [state, setState] = useState("Ready");
  const phase = useRef("Ready");
  const [error, setError] = useState("");
  const [automatic, setAutomatic] = useState(true);
  const [wakeEnabled, setWakeEnabled] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(true);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(
    () =>
      typeof document === "undefined" || document.visibilityState === "visible",
  );
  const capture = useRef<VoiceCapture | null>(null);
  const request = useRef<AbortController | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lease = useRef<(() => void) | null>(null);
  const armed = useRef(false);
  const generation = useRef(0);
  const lastSpoken = useRef("");
  const setPhase = useCallback((value: string) => {
    phase.current = value;
    setState(value);
  }, []);
  const stop = useCallback(
    (release = false) => {
      ++generation.current;
      capture.current?.cancel();
      capture.current = null;
      request.current?.abort();
      request.current = null;
      audio.current?.pause();
      audio.current = null;
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
      audioUrl.current = "";
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      if (release) {
        lease.current?.();
        lease.current = null;
      }
      setPhase("Ready");
    },
    [setPhase],
  );
  useEffect(() => () => stop(true), [stop]);
  useEffect(() => {
    let active = true;
    accountRequest<{ wake_enabled: boolean }>("/api/voice/settings")
      .then((data) => {
        if (active) setWakeEnabled(data.wake_enabled);
      })
      .catch(() => {
        if (active)
          setError(
            "Voice settings could not load. Talk and text remain available.",
          );
      })
      .finally(() => {
        if (active) setSettingsBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const changed = () => {
      setVisible(document.visibilityState === "visible");
      if (document.visibilityState !== "visible") {
        armed.current = false;
        stop(true);
      }
    };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, [stop]);

  async function speak(text: string) {
    stop();
    setError("");
    setPhase("Preparing speech…");
    const id = generation.current;
    const controller = new AbortController();
    request.current = controller;
    try {
      if (!lease.current) {
        const release = await acquireVoiceLease();
        if (id !== generation.current) {
          release();
          return;
        }
        lease.current = release;
      }
      const data = (await voiceRequest(
        "speak",
        { text: text.replace(/[*#`]/g, "").slice(0, 600) },
        controller.signal,
      )) as Blob;
      if (id !== generation.current) return;
      audioUrl.current = URL.createObjectURL(data);
      const player = new Audio(audioUrl.current);
      audio.current = player;
      player.onended = () => {
        if (id === generation.current) stop(!wakeEnabled);
      };
      player.onerror = () => {
        if (id === generation.current) {
          setPaused(true);
          stop(true);
          setError("Audio could not play. Text remains available.");
        }
      };
      await player.play();
      if (id === generation.current) setPhase("Speaking…");
    } catch (failure) {
      if (id === generation.current && !controller.signal.aborted) {
        setPaused(true);
        stop(true);
        setError(
          failure instanceof Error
            ? failure.message
            : "Speech could not play. Try Read reply.",
        );
      }
    }
  }

  async function finish(id: number, wake: boolean) {
    if (id !== generation.current || !capture.current) return;
    const recording = capture.current;
    capture.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (wake && !recording.heardSpeech) {
      recording.cancel();
      setPhase("Ready");
      return;
    }
    const data = recording.finish();
    const controller = new AbortController();
    request.current = controller;
    setPhase(wake ? "Checking for THRYV…" : "Transcribing…");
    try {
      let text: string;
      if (wake) {
        const result = (await voiceRequest(
          "wake",
          data,
          controller.signal,
        )) as WakeResult;
        if (id !== generation.current) return;
        if (!result.detected) {
          setPhase("Ready");
          return;
        }
        if (!result.command) {
          await start(false, true);
          return;
        }
        text = result.command;
      } else {
        text = (await voiceRequest(
          "transcribe",
          data,
          controller.signal,
        )) as string;
      }
      if (id !== generation.current) return;
      armed.current = true;
      lastSpoken.current = reply;
      setPhase("Processing reply…");
      await onTranscript(text);
      if (id === generation.current) setPhase("Ready");
    } catch (failure) {
      if (id === generation.current && !controller.signal.aborted) {
        setPaused(true);
        stop(true);
        setError(
          failure instanceof Error
            ? failure.message
            : "Speech failed. You can still type.",
        );
      }
    }
  }

  async function start(wake = false, afterKeyword = false) {
    stop();
    armed.current = false;
    setError("");
    setPhase("Requesting microphone…");
    const id = generation.current;
    const recording = new VoiceCapture(() => void finish(id, wake));
    capture.current = recording;
    try {
      if (!lease.current) {
        const release = await acquireVoiceLease();
        if (id !== generation.current) {
          release();
          return;
        }
        lease.current = release;
      }
      if ((await recording.start()) && id === generation.current) {
        setPhase(wake ? "Wake listening for THRYV…" : "Listening…");
        timer.current = setTimeout(
          () => {
            if (id !== generation.current) return;
            if (afterKeyword && !recording.heardSpeech) {
              stop();
              return;
            }
            void finish(id, wake);
          },
          afterKeyword ? 10000 : 30000,
        );
      }
    } catch (failure) {
      recording.cancel();
      if (id === generation.current) {
        setPaused(true);
        stop(true);
        setError(
          failure instanceof Error &&
            failure.message.includes("another THRYV tab")
            ? failure.message
            : "Microphone unavailable or permission denied. You can still type.",
        );
      }
    }
  }

  // A single scheduler prioritizes the final reply over restarting wake capture.
  // The phase ref changes synchronously, guarding repeated effects and late callbacks.
  const advance = useEffectEvent(() => {
    if (!visible || busy || waitingForDevice || phase.current !== "Ready")
      return;
    if (armed.current && automatic && reply && lastSpoken.current !== reply) {
      lastSpoken.current = reply;
      void speak(reply);
      return;
    }
    if (wakeEnabled && !paused && !settingsBusy) {
      void start(true);
      return;
    }
    lease.current?.();
    lease.current = null;
  });
  useEffect(() => {
    advance();
  }, [
    state,
    reply,
    busy,
    waitingForDevice,
    automatic,
    wakeEnabled,
    paused,
    settingsBusy,
    visible,
  ]);

  async function toggleWake(next: boolean) {
    if (settingsBusy) return;
    const previous = wakeEnabled;
    armed.current = false;
    stop(true);
    setPaused(!next);
    setWakeEnabled(next);
    setSettingsBusy(true);
    setError("");
    try {
      const data = await accountRequest<{ wake_enabled: boolean }>(
        "/api/voice/settings",
        "POST",
        { wake_enabled: next },
      );
      setWakeEnabled(data.wake_enabled);
    } catch {
      setWakeEnabled(previous);
      setPaused(true);
      setError(
        "Wake setting could not be saved. Microphone listening is paused.",
      );
    } finally {
      setSettingsBusy(false);
    }
  }
  const recording = state === "Listening…";
  const wakeListening = state === "Wake listening for THRYV…";
  return (
    <section className="voice-controls" aria-label="Voice">
      <div className="voice-buttons">
        <button
          type="button"
          onClick={() =>
            recording ? void finish(generation.current, false) : void start()
          }
          disabled={
            busy ||
            (!recording &&
              !wakeListening &&
              !["Ready", "Speaking…"].includes(state))
          }
          aria-label={recording ? "Finish voice message" : "Talk to THRYV"}
        >
          <Mic size={16} />
          {recording ? "Finish & send" : "Talk"}
        </button>
        <button
          type="button"
          onClick={() => {
            armed.current = false;
            void speak(reply);
          }}
          disabled={!reply || busy || recording}
        >
          <Volume2 size={16} /> Read reply
        </button>
        <button
          type="button"
          onClick={() => {
            armed.current = false;
            setPaused(true);
            stop(true);
          }}
          disabled={state === "Ready" && !wakeEnabled}
        >
          <Square size={14} /> Stop voice
        </button>
        <span role="status">
          {waitingForDevice && state === "Ready"
            ? "Waiting for device…"
            : state}
        </span>
        <label>
          <input
            type="checkbox"
            checked={automatic}
            onChange={(e) => {
              setAutomatic(e.target.checked);
              if (!e.target.checked) stop();
            }}
          />{" "}
          Speak voice replies
        </label>
      </div>
      <details className="voice-settings">
        <summary>Settings</summary>
        <fieldset>
          <legend>Voice</legend>
          <label>
            <input
              type="checkbox"
              checked={wakeEnabled}
              disabled={settingsBusy}
              onChange={(e) => void toggleWake(e.target.checked)}
            />{" "}
            Wake word (Beta): {wakeEnabled ? "On" : "Off"}
          </label>
          <p>
            Beta may miss invocations or mis-detect similar-sounding words. Talk
            is the recommended reliable fallback. THRYV is the fixed keyword.
          </p>
          <p>
            Say “Thryv” or “Hey Thryv, …”. This saved account setting enables
            microphone listening in one visible tab. Speech recognition runs on
            your THRYV server; unrecognized speech is discarded and never sent
            to DeepSeek.
          </p>
          {wakeEnabled && paused && (
            <button
              type="button"
              onClick={() => {
                setPaused(false);
                setError("");
              }}
            >
              Resume wake listening
            </button>
          )}
        </fieldset>
      </details>
      <small>
        Talk, then pause for about 1.3 seconds to send. Finish &amp; send and
        Stop voice are fallbacks. Up to 30 seconds; speech is processed on this
        THRYV server. Replies read up to 600 characters.{" "}
        {wakeEnabled && paused ? "Wake listening is paused." : ""}
      </small>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
