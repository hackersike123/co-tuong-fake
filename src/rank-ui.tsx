import { getCultivationRank } from "./ranks";
import { intlLocale } from "./i18n-core";
import { useLanguage } from "./i18n";

export function RankBadge({ elo, compact = false }: { elo: number; compact?: boolean }) {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const rank = getCultivationRank(elo);
  return (
    <span
      className={`cultivation-badge cultivation-${rank.index} ${compact ? "compact" : ""}`}
      title={`${rank.label} · ${rank.elo.toLocaleString(locale)} Elo`}
    >
      <span className="cultivation-gem" aria-hidden="true" />
      {rank.name}
      <span className="cultivation-layer">{`Tầng ${rank.layer}`}</span>
    </span>
  );
}

export function RankProgress({ elo, showNote = true }: { elo: number; showNote?: boolean }) {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const rank = getCultivationRank(elo);
  return (
    <div className={`cultivation-progress cultivation-${rank.index}`}>
      <div className="between">
        <RankBadge elo={elo} />
        <span className="small muted">{Math.floor(rank.progress)}%</span>
      </div>
      <div
        className="cultivation-progress-track"
        role="progressbar"
        aria-label={`Tiến trình tu luyện ${rank.name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.floor(rank.progress)}
        aria-valuetext={`${rank.label}, ${rank.elo.toLocaleString(locale)} Elo. ${
          rank.next
            ? `Còn ${rank.remaining.toLocaleString(locale)} Elo để đạt ${rank.next.name}.`
            : "Đã đạt cảnh giới cao nhất trong cấu hình hiện tại."
        }`}
      >
        <span style={{ width: `${rank.progress}%` }} />
      </div>
      <div className="small muted">
        {rank.next
          ? `Còn ${rank.remaining.toLocaleString(locale)} Elo để đột phá ${rank.next.name}`
          : "Đã đạt cảnh giới cao nhất trong cấu hình hiện tại."}
      </div>
      {showNote && <span className="tiny muted">Ngưỡng cảnh giới riêng của Kỳ Tiên Hội.</span>}
    </div>
  );
}
