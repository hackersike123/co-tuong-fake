import { useEffect, type CSSProperties } from "react";
import { Button, IconButton } from "@figma/astraui";
import { Volume2, VolumeX } from "lucide-react";
import { useExperience } from "./Experience";
import { useApp } from "../context";

export function ArenaAtmosphere() {
  const { settings, reducedMotion } = useExperience();
  if (!settings.effects) return null;
  return (
    <div className={`arena-atmosphere ${reducedMotion ? "motion-still" : ""}`} aria-hidden="true">
      <div className="arena-mist first" />
      <div className="arena-mist second" />
      {Array.from({ length: 6 }, (_, index) => (
        <span
          className="arena-spirit"
          key={index}
          style={{ "--spirit-index": index } as CSSProperties}
        />
      ))}
    </div>
  );
}

export function BoardYinYang() {
  const { settings, reducedMotion } = useExperience();
  if (!settings.effects || !settings.yinYang) return null;
  return (
    <div className={`board-energy-layer ${reducedMotion ? "motion-still" : ""}`} aria-hidden="true">
      <div className="yin-yang-halo" />
      <div className="yin-yang-symbol" />
    </div>
  );
}

export function SoundToggle() {
  const { soundEnabled, audioPending, audioError, toggleSound } = useExperience();
  const { notify } = useApp();
  useEffect(() => {
    if (audioError) notify(audioError, "error");
  }, [audioError]);
  const label = soundEnabled ? "Tắt âm thanh" : "Bật âm thanh";
  return (
    <span className="sound-toggle">
      <IconButton
        variant="subtle"
        icon={soundEnabled ? <Volume2 size={19} /> : <VolumeX size={19} />}
        aria-label={label}
        title={label}
        aria-pressed={soundEnabled}
        disabled={audioPending}
        onClick={() => void toggleSound()}
      />
    </span>
  );
}

export function CheckmateEffect({
  message,
  detail,
  onSkip,
}: {
  message: string;
  detail?: string;
  onSkip: () => void;
}) {
  return (
    <div className="checkmate-effect" role="status" aria-label="Hiệu ứng chiếu bí">
      <div className="checkmate-energy" aria-hidden="true" />
      <div className="checkmate-ring" aria-hidden="true" />
      <div className="checkmate-copy">
        <span className="eyebrow">LINH KHÍ HỘI TỤ</span>
        <div className="checkmate-title">CHIẾU BÍ</div>
        <div>{message}</div>
        {detail && <div className="small">{detail}</div>}
        <span className="small">Kết quả ván đấu</span>
        <Button variant="neutral" size="small" onClick={onSkip}>
          Bỏ qua hiệu ứng
        </Button>
      </div>
    </div>
  );
}
