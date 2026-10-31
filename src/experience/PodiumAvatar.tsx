import { Avatar } from "@figma/astraui";
import { useExperience } from "./Experience";
import { playerInitials } from "../data";

export type PodiumRank = 1 | 2 | 3;

const PODIUM_FRAMES = {
  1: { name: "khung-vip-314-v2", size: 244 },
  2: { name: "khung-vip-moc-3", size: 180 },
  3: { name: "khung-vip-moc-4", size: 180 },
} as const;

export function PodiumAvatar({
  rank,
  name,
  initials,
  tone,
  avatarUrl,
  current,
  compact = false,
}: {
  rank: PodiumRank;
  name: string;
  initials: string;
  tone: string;
  avatarUrl?: string;
  current: boolean;
  compact?: boolean;
}) {
  const { avatar, reducedMotion, settings, profile } = useExperience();
  const image = current ? avatar : avatarUrl;
  const displayName = current ? profile.name : name;
  const displayInitials = current ? playerInitials(profile.name) : initials;
  const displayTone = current ? profile.tone : tone;
  const frame = PODIUM_FRAMES[rank];
  const animate = !reducedMotion && settings.effects;
  // CSS cannot pause an animated WebP; the lossless first frame keeps its alpha.
  const extension = animate ? ".webp" : "-still.png";
  return (
    <div
      className={`podium-avatar vip-frame-${rank} ${
        compact ? "vip-frame-compact" : ""
      } ${animate ? "vip-frame-animated" : "vip-frame-still"}`}
      role="img"
      aria-label={`Ảnh đại diện ${displayName} trong khung Top ${rank}${
        image ? "" : " · chưa có ảnh, hiển thị chữ viết tắt"
      }`}
    >
      <div className="vip-frame-stage">
        <div className="podium-portrait-slot">
          <Avatar
            type={image ? "image" : "initial"}
            src={image || undefined}
            alt={`Ảnh đại diện ${displayName}`}
            initials={displayInitials}
            size="large"
            className={`user-avatar podium-portrait tone-${displayTone}`}
          />
        </div>
        <img
          className="podium-frame"
          src={`/images/podium/${frame.name}${extension}`}
          width={frame.size}
          height={frame.size}
          alt=""
          aria-hidden="true"
          draggable={false}
          decoding="async"
        />
        {animate && (
          <div className="vip-frame-effects" aria-hidden="true">
            <span className="vip-frame-halo" />
            <span className="vip-frame-trail" />
            <span className="vip-frame-spark spark-one" />
            <span className="vip-frame-spark spark-two" />
            <span className="vip-frame-spark spark-three" />
          </div>
        )}
      </div>
    </div>
  );
}
