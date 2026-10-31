import { useEffect, useRef, type ComponentProps, type CSSProperties, type ReactNode } from "react";
import { Avatar, Badge, Button, IconButton, Modal, Tooltip } from "@figma/astraui";
import { ArrowRight, Clock, Eye, Lock, Users, Search, ChevronRight } from "lucide-react";
import type { Piece, Room, Side } from "./data";
import { initialPieces, playerInitials } from "./data";
import { pieceSymbol, type PieceType } from "./chess/pieces";
import { useApp } from "./context";
import { useExperience } from "./experience/Experience";
import { BoardYinYang } from "./experience/effects";
import { getCultivationRank } from "./ranks";
import { RankBadge } from "./rank-ui";

export function PieceGlyph({ side, type }: { side: Side; type: PieceType }) {
  return (
    <span className="piece-glyph" lang="zh-Hant" aria-hidden="true">
      {pieceSymbol(side, type)}
    </span>
  );
}

export function Dialog(props: ComponentProps<typeof Modal>) {
  const initialFocus = useRef(document.activeElement as HTMLElement | null);
  useEffect(() => {
    if (!props.isOpen) return;
    const dialog = document.querySelector<HTMLElement>(".kydao-dialog");
    if (!dialog) return;
    const previousFocus = dialog.contains(document.activeElement)
      ? initialFocus.current
      : (document.activeElement as HTMLElement | null);
    // Astra's modal needs a localized close label and a keyboard focus boundary.
    const closeButton = dialog.querySelector<HTMLButtonElement>(
      ":scope > div:first-child > button",
    );
    closeButton?.setAttribute("aria-label", "Đóng hộp thoại");
    closeButton?.setAttribute("title", "Đóng hộp thoại");
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input:not(:disabled), [tabindex='0']",
        ),
      ).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
    if (!dialog.contains(document.activeElement)) {
      focusable()[0]?.focus({ preventScroll: true });
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const elements = focusable();
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (
        event.shiftKey &&
        (document.activeElement === first || !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      if (!dialog.isConnected && previousFocus?.isConnected)
        previousFocus.focus({ preventScroll: true });
    };
  }, [props.isOpen]);
  return <Modal {...props} className={`kydao-dialog ${props.className || ""}`} />;
}

export function Heading({
  children,
  level = 2,
  className = "",
}: {
  children: ReactNode;
  level?: number;
  className?: string;
}) {
  return (
    <div role="heading" aria-level={level} className={`heading heading-${level} ${className}`}>
      {children}
    </div>
  );
}

export function UserAvatar({
  initials = "MA",
  tone = "sage",
  size = "large",
  className = "",
  elo = 1000,
  current = false,
  image: previewImage,
}: {
  initials?: string;
  tone?: string;
  size?: "small" | "medium" | "large";
  className?: string;
  elo?: number;
  current?: boolean;
  image?: string | null;
}) {
  const { avatar, demoElo, profile } = useExperience();
  const rank = getCultivationRank(current ? demoElo : elo);
  const image = previewImage !== undefined ? previewImage : current ? avatar : null;
  const displayInitials = current ? playerInitials(profile.name) : initials;
  const displayTone = current ? profile.tone : tone;
  return (
    <Avatar
      type={image ? "image" : "initial"}
      src={image || undefined}
      alt={`${displayInitials} — ${rank.label}${image ? " — ảnh lưu cục bộ" : ""}`}
      initials={displayInitials}
      size={size}
      className={`user-avatar rank-framed cultivation-${rank.index} tone-${displayTone} ${className}`}
    />
  );
}

export function IconAction({
  label,
  icon,
  onClick,
  disabled = false,
  className = "",
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <Tooltip content={label}>
      <IconButton
        aria-label={label}
        title={label}
        icon={icon}
        onClick={onClick}
        disabled={disabled}
        variant="subtle"
        className={className}
      />
    </Tooltip>
  );
}

export function OnlineStatus({
  children = "Đang trực tuyến",
  muted = false,
}: {
  children?: ReactNode;
  muted?: boolean;
}) {
  return (
    <span className={`online-status ${muted ? "muted" : ""}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

export function SectionTitle({
  title,
  subtitle,
  action,
  onAction,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="section-title">
      <div>
        <Heading>{title}</Heading>
        {subtitle && <div className="muted mt-xs">{subtitle}</div>}
      </div>
      {action && (
        <Button
          variant="subtle"
          size="small"
          iconEnd={<ArrowRight size={16} />}
          onClick={onAction}
          className="text-link"
        >
          {action}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  onAction,
  icon,
}: {
  title: string;
  description: string;
  action?: string;
  onAction?: () => void;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon || <Search size={28} strokeWidth={1.5} />}</span>
      <Heading level={3}>{title}</Heading>
      <div className="muted">{description}</div>
      {action && (
        <Button variant="neutral" onClick={onAction}>
          {action}
        </Button>
      )}
    </div>
  );
}

export function RoomCard({ room, compact = false }: { room: Room; compact?: boolean }) {
  const { joinRoom, signedIn } = useApp();
  const { demoElo } = useExperience();
  const current = signedIn && Boolean(room.ownedByMe);
  const rating = current ? demoElo : room.elo;
  return (
    <article className={`room-card ${compact ? "compact" : ""}`}>
      <div className="room-card-top">
        <span className={`room-time ${room.seconds === 15 ? "fast" : ""}`}>
          <Clock size={14} />
          {room.seconds}s / lượt
        </span>
        {room.private ? (
          <span title="Phòng riêng tư" className="muted">
            <Lock size={15} />
          </span>
        ) : (
          <span className={`room-status ${room.playing ? "playing" : ""}`}>
            <span className="status-dot" />
            {room.playing ? "Đang đấu" : "Đang chờ"}
          </span>
        )}
      </div>
      <Heading level={3} className="room-name">
        {room.name}
      </Heading>
      <div className="room-host">
        <UserAvatar
          initials={room.initials}
          tone={room.tone}
          size="medium"
          elo={rating}
          current={current}
        />
        <div>
          <div className="player-name">{room.host}</div>
          <div className="small muted">{rating.toLocaleString("vi-VN")} Elo</div>
          <RankBadge elo={rating} compact />
        </div>
      </div>
      <div className="room-card-bottom">
        <span className="room-occupancy">
          <Users size={15} />
          {room.players}/2 <span className="room-code">#{room.id}</span>
        </span>
        <Button
          variant={room.playing ? "subtle" : "neutral"}
          size="small"
          iconEnd={room.playing ? <Eye size={15} /> : <ArrowRight size={15} />}
          onClick={() => joinRoom(room)}
          className="room-join"
        >
          {room.playing ? "Xem đấu" : "Vào phòng"}
        </Button>
      </div>
    </article>
  );
}

export function ChessBoard({
  pieces = initialPieces(),
  interactive = false,
  selected,
  onSquare,
  hint,
  flipped = false,
  small = false,
  lastMove,
}: {
  pieces?: Piece[];
  interactive?: boolean;
  selected?: string | null;
  onSquare?: (x: number, y: number) => void;
  hint?: {
    x: number;
    y: number;
  } | null;
  flipped?: boolean;
  small?: boolean;
  lastMove?: {
    x: number;
    y: number;
  } | null;
}) {
  const { settings } = useExperience();
  const style = (x: number, y: number) =>
    ({
      "--x": flipped ? 8 - x : x,
      "--y": flipped ? 9 - y : y,
    }) as CSSProperties;
  return (
    <div
      className={`chess-board ${small ? "board-small" : ""}`}
      aria-label="Bàn cờ tướng 9 cột, 10 hàng"
    >
      <div className="board-surface">
        <div className="board-grid">
          {Array.from({ length: 10 }, (_, i) => (
            <div
              key={`h${i}`}
              className="board-horizontal"
              style={{ "--line-index": i } as CSSProperties}
            />
          ))}
          {Array.from({ length: 9 }, (_, i) => (
            <div key={`v${i}`} style={{ "--line-index": i } as CSSProperties}>
              <div className="board-vertical top" style={{ "--line-index": i } as CSSProperties} />
              <div
                className="board-vertical bottom"
                style={{ "--line-index": i } as CSSProperties}
              />
            </div>
          ))}
          <div className="palace-cross" />
          <div className="palace-cross reverse" />
          <div className="palace-cross lower" />
          <div className="palace-cross reverse lower" />
          <div className="board-river">
            <span>SỞ HÀ</span>
            <span>HÁN GIỚI</span>
          </div>
          {[0, 2, 4, 6, 8].flatMap((x) =>
            [3, 6].map((y) => (
              <span key={`mark${x}${y}`} className="board-mark" style={style(x, y)} />
            )),
          )}
          <BoardYinYang />
          {interactive
            ? Array.from({ length: 90 }, (_, i) => {
                const x = i % 9,
                  y = Math.floor(i / 9);
                const piece = pieces.find((p) => p.x === x && p.y === y);
                return (
                  <Button
                    key={i}
                    variant="subtle"
                    className={`board-square ${
                      piece ? `board-piece piece-${piece.side}` : "square-empty"
                    } ${piece?.id === selected ? "piece-selected" : ""} ${
                      hint?.x === x && hint.y === y ? "square-hint" : ""
                    } ${
                      settings.highlightMoves && lastMove?.x === x && lastMove.y === y
                        ? "square-last"
                        : ""
                    }`}
                    style={style(x, y)}
                    onClick={() => onSquare?.(x, y)}
                    aria-label={
                      piece
                        ? `${piece.label} ${
                            piece.side === "red" ? "Đỏ" : "Đen"
                          }, cột ${x + 1}, hàng ${y + 1}`
                        : `Ô trống cột ${x + 1}, hàng ${y + 1}`
                    }
                    aria-pressed={piece?.id === selected}
                  >
                    {piece ? (
                      <PieceGlyph side={piece.side} type={piece.label} />
                    ) : (
                      <span className="square-marker" />
                    )}
                  </Button>
                );
              })
            : pieces.map((piece) => (
                <div
                  key={piece.id}
                  className={`board-square board-piece piece-${piece.side}`}
                  style={style(piece.x, piece.y)}
                >
                  <PieceGlyph side={piece.side} type={piece.label} />
                </div>
              ))}
        </div>
      </div>
      {!small && (
        <div className="board-coordinates">
          {Array.from({ length: 9 }, (_, i) => (
            <span key={i}>{flipped ? i + 1 : 9 - i}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function PlayerStrip({
  name,
  initials,
  elo,
  side,
  active,
  time = "00:30",
  computer = false,
  tone = "sage",
  waiting = false,
  current = false,
  winner = false,
}: {
  name: string;
  initials: string;
  elo: number;
  side: Side;
  active?: boolean;
  time?: string;
  computer?: boolean;
  tone?: string;
  waiting?: boolean;
  current?: boolean;
  winner?: boolean;
}) {
  const { demoElo } = useExperience();
  const rating = current ? demoElo : elo;
  return (
    <div
      className={`player-strip ${active ? "player-active" : ""} ${winner ? "player-winner" : ""}`}
    >
      <UserAvatar initials={initials} tone={tone} elo={rating} current={current} />
      <div className="player-strip-info">
        <div className="player-name">
          {name}
          {computer && <Badge label="Máy" variant="secondary" />}
        </div>
        <div className="small muted">
          <span className={`piece-dot ${side}`} />
          Quân {side === "red" ? "Đỏ" : "Đen"}
          <span className="meta-dot">·</span>
          {rating.toLocaleString("vi-VN")} Elo
        </div>
        <RankBadge elo={rating} compact />
      </div>
      {waiting ? (
        <Badge label="Đang chờ" variant="secondary" />
      ) : (
        <div className={`player-clock ${active ? "clock-active" : ""}`}>
          <Clock size={17} />
          {time}
        </div>
      )}
    </div>
  );
}

export function BreadcrumbBack({
  label = "Về sảnh chính",
  page = "home",
}: {
  label?: string;
  page?: "home" | "history" | "rooms";
}) {
  const { go } = useApp();
  return (
    <Button
      variant="subtle"
      size="small"
      onClick={() => go(page)}
      iconStart={<ChevronRight size={16} className="rotate-180" />}
      className="back-link"
    >
      {label}
    </Button>
  );
}
