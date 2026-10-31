import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type Context,
  type ReactNode,
} from "react";
import { INITIAL_DEMO_ELO } from "../ranks";
import type { PieceType } from "../chess/pieces";
import { ChessAudio, type AudioCue } from "./audio";
import { useLocalProfile } from "./useLocalProfile";

const SETTINGS_STORAGE_KEY = "ky-tien-hoi.demo.settings.v1";
export type MotionPreference = "system" | "reduce" | "allow";
const DEFAULT_SETTINGS = {
  effects: true,
  yinYang: true,
  motionPreference: "system" as MotionPreference,
  highlightMoves: true,
  quietAudio: true,
  volume: 0.35,
};
export type ExperienceSettings = typeof DEFAULT_SETTINGS;
type ExperienceValue = ReturnType<typeof useLocalProfile> & {
  avatar: string | null;
  demoElo: number;
  applyDemoElo: (change: number) => void;
  settings: ExperienceSettings;
  updateSettings: (value: Partial<ExperienceSettings>) => void;
  systemReducedMotion: boolean;
  reducedMotion: boolean;
  soundEnabled: boolean;
  audioPending: boolean;
  audioError: string;
  toggleSound: () => Promise<void>;
  playMove: (piece: PieceType, captured?: boolean) => void;
  playCue: (cue: AudioCue) => void;
  stopSound: () => void;
  storageError: string;
};

function storedSettings(): ExperienceSettings {
  try {
    const value = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || "{}");
    const result = { ...DEFAULT_SETTINGS };
    for (const key of ["effects", "yinYang", "highlightMoves", "quietAudio"] as const) {
      if (typeof value[key] === "boolean") result[key] = value[key];
    }
    if (["system", "reduce", "allow"].includes(value.motionPreference))
      result.motionPreference = value.motionPreference;
    else if (value.reducedMotion === true) result.motionPreference = "reduce";
    if (typeof value.volume === "number" && Number.isFinite(value.volume))
      result.volume = Math.max(0, Math.min(1, value.volume));
    return result;
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

const hotData: { experienceContext?: Context<ExperienceValue | null> } | undefined = import.meta.hot
  ?.data;
// Provider and hook imports can refresh at different times; keep their context identical.
const ExperienceContext = hotData?.experienceContext ?? createContext<ExperienceValue | null>(null);
if (hotData) hotData.experienceContext = ExperienceContext;

export function ExperienceProvider({ children }: { children: ReactNode }) {
  const localProfile = useLocalProfile();
  const [demoElo, setDemoElo] = useState(INITIAL_DEMO_ELO);
  const [settings, setSettings] = useState(storedSettings);
  const [systemReducedMotion, setSystemReducedMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const reducedMotion =
    settings.motionPreference === "reduce" ||
    (settings.motionPreference !== "allow" && systemReducedMotion);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [audioPending, setAudioPending] = useState(false);
  const [audioError, setAudioError] = useState("");
  const [storageError, setStorageError] = useState("");
  const audio = useRef<ChessAudio | null>(null);
  if (!audio.current) audio.current = new ChessAudio();
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setSystemReducedMotion(query.matches);
    onChange();
    query.addEventListener("change", onChange);
    const stopInBackground = () => {
      if (document.hidden) audio.current?.stop();
    };
    document.addEventListener("visibilitychange", stopInBackground);
    return () => {
      query.removeEventListener("change", onChange);
      document.removeEventListener("visibilitychange", stopInBackground);
      audio.current?.dispose();
    };
  }, []);
  useEffect(() => {
    audio.current?.configure(settings.volume, settings.quietAudio || reducedMotion);
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
      setStorageError("");
    } catch {
      setStorageError("Trình duyệt không cho lưu tùy chọn. Các thay đổi chỉ dùng trong phiên này.");
    }
  }, [settings, reducedMotion]);
  const toggleSound = async () => {
    if (audioPending) return;
    if (soundEnabled) {
      audio.current?.mute();
      setSoundEnabled(false);
      return;
    }
    try {
      setAudioError("");
      setAudioPending(true);
      await audio.current!.enable();
      setSoundEnabled(true);
    } catch (error) {
      setSoundEnabled(false);
      setAudioError(
        error instanceof Error ? error.message : "Chưa thể bật âm thanh. Vui lòng thử lại.",
      );
    } finally {
      setAudioPending(false);
    }
  };
  const applyDemoElo = useCallback((change: number) => {
    if (Number.isFinite(change))
      setDemoElo((value) => Math.max(0, Math.min(9999, value + Math.trunc(change))));
  }, []);
  return (
    <ExperienceContext.Provider
      value={{
        ...localProfile,
        avatar: localProfile.profile.imageUrl,
        demoElo,
        applyDemoElo,
        settings,
        updateSettings: (value) => setSettings((previous) => ({ ...previous, ...value })),
        systemReducedMotion,
        reducedMotion,
        soundEnabled,
        audioPending,
        audioError,
        toggleSound,
        storageError,
        playMove: (piece, captured) => audio.current?.playMove(piece, captured),
        playCue: (cue) => audio.current?.play(cue),
        stopSound: () => audio.current?.stop(),
      }}
    >
      {children}
    </ExperienceContext.Provider>
  );
}

export function useExperience() {
  const value = useContext(ExperienceContext);
  if (!value) throw new Error("ExperienceProvider is required");
  return value;
}
