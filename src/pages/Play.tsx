import { useEffect, useMemo, useRef, useState } from "react"
import {
  Badge,
  Button,
  InputField,
  SelectField,
  Tabs,
} from "@figma/astraui"
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Clock,
  Copy,
  Eye,
  Flag,
  Handshake,
  Lightbulb,
  LogOut,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Send,
  Share2,
  ShieldCheck,
  Smile,
  Sprout,
  Swords,
  Target,
  Trophy,
  UserPlus,
  Users,
  WifiOff,
  X,
} from "lucide-react"
import {
  BreadcrumbBack,
  ChessBoard,
  Dialog as Modal,
  Heading,
  IconAction,
  PieceGlyph,
  PlayerStrip,
  SectionTitle,
  UserAvatar,
} from "../components"
import { useApp, type RoomAccess } from "../context"
import { formatClock, initialPieces, piecesFromFen, playerInitials, replayMoves, resultLabels } from "../data"
import type { ChessMove, Piece, Side } from "../data"
import { useExperience } from "../experience/Experience"
import { ArenaAtmosphere, CheckmateEffect, SoundToggle } from "../experience/effects"
import { RankProgress } from "../rank-ui"
import { websocketUrl } from "../config/connection"

const difficultyOptions = [
  {
    id: "easy",
    name: "Dễ",
    description: "Làm quen bàn cờ, thoải mái khám phá.",
    icon: Sprout,
    label: "Dành cho người mới",
  },
  {
    id: "medium",
    name: "Trung bình",
    description: "Thử thách vừa sức, rèn luyện tư duy.",
    icon: Bot,
    label: "Được yêu thích",
  },
  {
    id: "hard",
    name: "Khó",
    description: "Tính toán sâu hơn, bứt phá giới hạn.",
    icon: Target,
    label: "Dành cho kỳ thủ",
  },
]

export function AISetup() {
  const { startGame, openModal } = useApp()
  const [side, setSide] = useState<Side>("red")
  const [difficulty, setDifficulty] = useState("medium")
  return (
    <div className="page-stack ai-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">LUYỆN TẬP MỖI NGÀY</div>
          <Heading level={1}>Kỳ hữu luôn sẵn sàng</Heading>
          <div className="muted mt-xs">
            Một đối thủ kiên nhẫn. Một không gian để tiến bộ.
          </div>
        </div>
        <BreadcrumbBack />
      </div>
      <div className="setup-grid">
        <section className="setup-board-panel">
          <div className="setup-board-intro">
            <span className="quick-icon tone-sand">
              <Bot size={24} />
            </span>
            <div>
              <Heading>Chơi theo nhịp của bạn</Heading>
              <div className="muted small">
                Không áp lực Elo. Tự do thử nghiệm.
              </div>
            </div>
          </div>
          <div className="setup-board">
            <ChessBoard flipped={side === "black"} />
          </div>
          <div className="setup-board-note">
            <ShieldCheck size={17} />
            Ván với máy không ảnh hưởng đến điểm xếp hạng.
          </div>
        </section>
        <section className="surface setup-options">
          <div>
            <Heading>Thiết lập ván cờ</Heading>
            <div className="muted small mt-xs">
              Chọn màu quân và thử thách phù hợp.
            </div>
          </div>
          <div>
            <div className="form-label">Bạn muốn cầm quân nào?</div>
            <div className="side-choices">
              {(["red", "black"] as Side[]).map((color) => (
                <Button
                  key={color}
                  variant="neutral"
                  className={`side-choice ${side === color ? "chosen" : ""}`}
                  onClick={() => setSide(color)}
                >
                  <span className={`choice-piece ${color}`}><PieceGlyph side={color} type="Tướng" /></span>
                  <span>
                    <span className="player-name">
                      Quân {color === "red" ? "Đỏ" : "Đen"}
                    </span>
                    <span className="muted small">
                      {color === "red"
                        ? "Đi trước · Chủ động khai cuộc"
                        : "Đi sau · Quan sát, phản công"}
                    </span>
                  </span>
                  <span className="choice-check">
                    {side === color && <Check size={13} />}
                  </span>
                </Button>
              ))}
            </div>
          </div>
          <div>
            <div className="form-label">Chọn độ khó</div>
            <div className="difficulty-choices">
              {difficultyOptions.map(
                ({ id, name, description, icon: Icon, label }) => (
                  <Button
                    key={id}
                    variant="neutral"
                    className={`difficulty-choice ${
                      difficulty === id ? "chosen" : ""
                    }`}
                    onClick={() => setDifficulty(id)}
                  >
                    <span
                      className={`quick-icon ${
                        id === "easy"
                          ? "tone-sage"
                          : id === "medium"
                            ? "tone-sand"
                            : "tone-rose"
                      }`}
                    >
                      <Icon size={22} />
                    </span>
                    <span className="grow">
                      <span className="between">
                        <span className="player-name">{name}</span>
                        {difficulty === id && (
                          <span className="tiny difficulty-tag">{label}</span>
                        )}
                      </span>
                      <span className="muted small">{description}</span>
                    </span>
                    <span className="choice-check">
                      {difficulty === id && <Check size={13} />}
                    </span>
                  </Button>
                ),
              )}
            </div>
          </div>
          <div className="info-message">
            <Lightbulb size={17} />
            <span>
              Bạn có thể đi lại hoặc nhờ gợi ý bất cứ lúc nào. Cứ thử một nước
              cờ mới!
            </span>
          </div>
          <Button
            className="button-full start-game-button"
            iconEnd={<ArrowRight size={17} />}
            onClick={() => startGame("ai", side, difficulty)}
          >
            Bắt đầu ván cờ
          </Button>
          <Button
            variant="subtle"
            size="small"
            className="text-link"
            onClick={() => openModal("rules")}
          >
            Luật cờ tướng
          </Button>
        </section>
      </div>
    </div>
  )
}

export function GameChat({
  spectator = false,
  waiting = false,
}: {
  spectator?: boolean
  waiting?: boolean
}) {
  const { username, signedIn, roomAccess } = useApp()
  const messagesRef = useRef<HTMLDivElement>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const [messages, setMessages] = useState<Array<{
    id: string | number
    name: string
    text: string
    time: string
    own: boolean
  }>>([])
  const [text, setText] = useState("")
  const [reactions, setReactions] = useState(false)
  useEffect(() => {
    if (!roomAccess) return
    const access = roomAccess
    let stopped = false
    let socket: WebSocket | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    function connect() {
      const params = new URLSearchParams({ participant_token: access.participant_token })
      socket = new WebSocket(websocketUrl(`/api/v1/rooms/${access.id}/ws?${params.toString()}`))
      socketRef.current = socket
      socket.onopen = () => { attempt = 0 }
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            type?: string
            message_id?: string
            role?: RoomAccess["role"]
            sender_name?: string
            text?: string
            sent_at?: number
          }
          if (payload.type !== "chat_message" || !payload.text) return
          setMessages((current) => [...current, {
            id: payload.message_id || `${Date.now()}-${current.length}`,
            name: payload.sender_name || "Kỳ hữu",
            text: payload.text || "",
            time: new Date(payload.sent_at || Date.now()).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
            own: payload.role === access.role,
          }])
        } catch {
          return
        }
      }
      socket.onclose = () => {
        if (!stopped) retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000))
      }
    }
    const connectTimer = setTimeout(connect, 0)
    return () => {
      stopped = true
      clearTimeout(connectTimer)
      if (retryTimer) clearTimeout(retryTimer)
      if (socketRef.current === socket) socketRef.current = null
      socket?.close(1000, "Chat component closed")
    }
  }, [roomAccess?.id, roomAccess?.participant_token, roomAccess?.role])
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages])
  function send(value: string) {
    if (!value.trim()) return
    const socket = socketRef.current
    if (!roomAccess || !socket || socket.readyState !== WebSocket.OPEN) return
    socket.send(JSON.stringify({
      type: "chat_message",
      sender_name: signedIn ? username : "Kỳ hữu",
      text: value.trim(),
    }))
    setText("")
    setReactions(false)
  }
  return (
    <div className="game-chat">
      {spectator && (
        <div className="chat-spectator-note">
          <Eye size={14} />
          Bạn đang trò chuyện với tư cách khán giả.
        </div>
      )}
      <div
        ref={messagesRef}
        className="chat-messages"
        role="log"
        aria-label="Tin nhắn trong phòng"
        aria-live="polite"
      >
        {messages.map((message) => (
          <div
            className={`chat-message ${message.own ? "own" : ""}`}
            key={message.id}
          >
            <div className="chat-message-meta">
              <span>{message.name}</span>
              <span>{message.time}</span>
            </div>
            <div className="chat-message-text">{message.text}</div>
          </div>
        ))}
      </div>
      {reactions && (
        <div className="reaction-picker">
          {["👍", "👏", "🤝", "😊"].map((reaction) => (
            <Button
              key={reaction}
              variant="subtle"
              onClick={() => send(reaction)}
            >
              {reaction}
            </Button>
          ))}
        </div>
      )}
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        <InputField
          aria-label="Tin nhắn"
          placeholder="Gửi lời chào kỳ hữu..."
          value={text}
          onChange={setText}
          maxLength={300}
        />
        <IconAction
          label="Biểu tượng cảm xúc"
          icon={<Smile size={19} />}
          onClick={() => setReactions((v) => !v)}
        />
        <Button
          type="submit"
          variant="subtle"
          disabled={!text.trim()}
          aria-label="Gửi tin nhắn"
          className="chat-send"
        >
          <Send size={17} />
        </Button>
      </form>
      <div className="chat-guideline">Giao lưu văn minh, tôn trọng kỳ hữu.</div>
    </div>
  )
}

export function WaitingRoom() {
  const { demoElo } = useExperience()
  const {
    activeRoom,
    go,
    username,
    openModal,
    startGame,
    notify,
    request,
    roomAccess,
    setRoomAccess,
  } = useApp()
  const [role, setRole] = useState(
    roomAccess?.role === "player1" ? "host" : roomAccess?.role === "spectator" ? "spectator" : "player",
  )
  const [opponent, setOpponent] = useState(false)
  const [ready, setReady] = useState(false)
  const [confirm, setConfirm] = useState<"kick" | "leave" | null>(null)
  const [loading, setLoading] = useState(false)
  const roomSocket = useRef<WebSocket | null>(null)
  const started = useRef(false)
  function openStartedGame() {
    if (started.current || !roomAccess) return
    started.current = true
    startGame(
      "online",
      roomAccess.role === "player2" ? "black" : "red",
      "medium",
      roomAccess.role === "spectator",
    )
  }
  useEffect(() => {
    if (!roomAccess) {
      notify("Thiếu thông tin xác thực phòng. Vào phòng lại từ sảnh.", "error")
      go("rooms")
      return
    }
    let socket: WebSocket | undefined
    let cancelled = false
    const connectTimer = setTimeout(() => {
      const query = new URLSearchParams({ participant_token: roomAccess.participant_token })
      socket = new WebSocket(
        websocketUrl(`/api/v1/rooms/${roomAccess.id}/ws?${query.toString()}`),
      )
      roomSocket.current = socket
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as {
            type?: string
            role?: RoomAccess["role"]
            room?: Record<string, unknown>
            game?: { fen: string; status: string; winner?: string | null }
            ready?: boolean
            reconnect_seconds?: number
          }
          if (event.type === "room.snapshot") {
            const eventRole = event.role || roomAccess.role
            setRole(eventRole === "player1" ? "host" : eventRole === "player2" ? "player" : "spectator")
            const summary = event.room
            setOpponent((Number(summary?.player_count) || 0) >= 2)
            setReady(Boolean(summary?.player2_ready))
            if (event.game?.status === "playing") openStartedGame()
          } else if (event.type === "room.participant_joined") {
            const joinedRole = event.role
            if (joinedRole === "player2") setOpponent(true)
          } else if (event.type === "player.ready") {
            setReady(Boolean(event.ready))
          } else if (event.type === "room.started") {
            openStartedGame()
          } else if (event.type === "room.closed") {
            notify("Phòng đã đóng.", "info")
            setRoomAccess(null)
            go("rooms")
          } else if (event.type === "error") {
            notify(String((event as { reason?: string }).reason || "Yêu cầu phòng không hợp lệ."), "error")
          }
        } catch {
          notify("Không đọc được sự kiện từ phòng.", "error")
        }
      }
      socket.onclose = () => {
        if (!cancelled && !started.current) notify("Kết nối phòng bị ngắt.", "error")
      }
    }, 0)
    return () => {
      cancelled = true
      clearTimeout(connectTimer)
      if (roomSocket.current === socket) roomSocket.current = null
      socket?.close(1000, "Waiting page closed")
    }
  }, [roomAccess?.id, roomAccess?.participant_token])
  const redPlayer = {
    name: role === "host" ? username : activeRoom.host,
    initials: role === "host" ? playerInitials(username) : activeRoom.initials,
    elo: role === "host" ? demoElo : activeRoom.elo,
    current: role === "host",
    side: "red" as Side,
    tone: "rose",
  }
  const blackPlayer = {
    name: opponent
      ? role === "player" ? username : "ThanhPhong"
      : "Đang chờ kỳ hữu mẫu...",
    initials: opponent
      ? role === "player" ? playerInitials(username) : "TP"
      : "?",
    elo: role === "player" ? demoElo : 1320,
    current: role === "player",
    side: "black" as Side,
    tone: "blue",
  }
  const topPlayer = role === "player" ? redPlayer : blackPlayer
  const bottomPlayer = role === "player" ? blackPlayer : redPlayer
  async function setOpponentReady() {
    if (!roomAccess) return
    setLoading(true)
    try {
      await request("room.ready", {
        room_id: roomAccess.id,
        participant_token: roomAccess.participant_token,
        ready: true,
      })
      setReady(true)
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể xác nhận sẵn sàng.", "error")
    } finally {
      setLoading(false)
    }
  }
  async function startRoomGame() {
    if (!roomAccess) return
    setLoading(true)
    try {
      await request("room.start", {
        room_id: roomAccess.id,
        participant_token: roomAccess.participant_token,
      })
      openStartedGame()
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể bắt đầu ván đấu.", "error")
    } finally {
      setLoading(false)
    }
  }
  async function leaveRoom() {
    if (!roomAccess) return go("rooms")
    try {
      await request("room.leave", {
        room_id: roomAccess.id,
        participant_token: roomAccess.participant_token,
      })
      setRoomAccess(null)
      go("rooms")
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể rời phòng.", "error")
    }
  }
  return (
    <div className="page-stack waiting-page">
      <ArenaAtmosphere />
      <div className="page-heading-row">
        <div>
          <div className="inline">
            <span className="eyebrow">PHÒNG CHỜ</span>
            <Badge
              label={activeRoom.private ? "Riêng tư" : "Công khai"}
              variant="secondary"
            />
          </div>
          <Heading level={1}>{activeRoom.name}</Heading>
          <div className="inline muted small mt-xs">
            <span>#{activeRoom.id}</span>
            <span className="meta-dot">·</span>
            <Clock size={14} />
            {activeRoom.seconds} giây / lượt<span className="meta-dot">·</span>
            <Users size={14} />
            {opponent ? "2" : "1"}/2 kỳ thủ
          </div>
        </div>
        <Button
          variant="neutral"
          iconStart={<LogOut size={16} />}
          onClick={() => setConfirm("leave")}
        >
          Rời phòng
        </Button>
      </div>
      <div className="match-layout">
        <section className="waiting-board-area">
          <PlayerStrip {...topPlayer} waiting />
          <div className="waiting-board-wrap">
            <ChessBoard flipped={role === "player"} />
            <div className="waiting-board-overlay">
              <span className="waiting-icon">
                <Users size={27} />
              </span>
              <Heading>
                {ready
                  ? "Đối thủ đã sẵn sàng"
                  : opponent
                    ? "Kỳ thủ đã có mặt"
                    : "Bàn cờ đã sẵn sàng"}
              </Heading>
              <div className="muted">
                {ready
                  ? "Chủ phòng có thể bắt đầu ván đấu."
                  : opponent
                    ? "Đối thủ đã vào phòng."
                    : "Chia sẻ mã hoặc liên kết để mời đối thủ."}
              </div>
              {opponent && !ready && role !== "spectator" && (
                <Button
                  variant="neutral"
                  iconStart={<Check size={16} />}
                  disabled={loading || role !== "player"}
                  onClick={setOpponentReady}
                >
                  {role === "player" ? "Sẵn sàng" : "Đối thủ chưa sẵn sàng"}
                </Button>
              )}
            </div>
          </div>
          <PlayerStrip {...bottomPlayer} waiting />
          <div className="waiting-main-actions">
            <div className="inline">
              <ShieldCheck size={17} className="muted" />
              <span className="small muted">
                {role === "host"
                  ? "Bạn là chủ phòng, cầm quân Đỏ và đi trước."
                  : role === "player"
                    ? "Bạn cầm quân Đen và đi sau."
                    : "Bạn là khán giả. Chỉ xem và trò chuyện."}
              </span>
            </div>
            {role !== "spectator" && (
              <Button
                iconStart={<Play size={16} />}
                disabled={!ready || !opponent || roomAccess?.role !== "player1" || loading}
                onClick={() => void startRoomGame()}
              >
                {roomAccess?.role === "player1" ? "Bắt đầu ván cờ" : "Chờ chủ phòng bắt đầu"}
              </Button>
            )}
          </div>
        </section>
        <aside className="match-aside">
          <section className="surface invite-panel">
            <SectionTitle title="Mời kỳ hữu" />
            <div className="muted small">
              Chia sẻ mã phòng và cùng nhau khai cuộc.
            </div>
            <div className="invite-code">
              <span>{activeRoom.id}</span>
              <IconAction
                label="Sao chép mã phòng"
                icon={<Copy size={18} />}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(activeRoom.id)
                    notify("Đã sao chép mã phòng.")
                  } catch {
                    notify("Hãy chọn và sao chép mã phòng ở trên.", "info")
                  }
                }}
              />
            </div>
            <Button
              variant="neutral"
              className="button-full"
              iconStart={<Share2 size={16} />}
              onClick={() => openModal("share")}
            >
              Chia sẻ lời mời
            </Button>
          </section>
          <section className="surface waiting-players">
            <SectionTitle title="Kỳ thủ trong phòng" />
            <div className="waiting-player">
              <UserAvatar initials={role === "host" ? playerInitials(username) : activeRoom.initials} tone="rose" size="medium" elo={activeRoom.elo} current={role === "host"} />
              <div className="grow">
                <div className="player-name">
                  {role === "host" ? username : activeRoom.host}
                </div>
                <span className="small muted">Chủ phòng · Quân Đỏ</span>
              </div>
              <Badge label="Chủ phòng" variant="brand" />
            </div>
            {opponent ? (
              <div className="waiting-player">
                <UserAvatar initials={role === "player" ? playerInitials(username) : "TP"} tone="sage" size="medium" elo={1320} current={role === "player"} />
                <div className="grow">
                  <div className="player-name">
                {role === "player" ? username : "Kỳ thủ thứ hai"}
                  </div>
                  <span className={`small ${ready ? "ready-text" : "muted"}`}>
                    {ready ? "Đã sẵn sàng" : "Chưa sẵn sàng"} · Quân Đen
                  </span>
                </div>
              </div>
            ) : (
              <div className="empty-player-slot">
                <UserPlus size={18} />
                Chờ người chơi thứ hai
              </div>
            )}
            <div className="spectators-count">
              <Eye size={15} />
              {activeRoom.spectators
                ? "Cho phép khán giả · 0 đang xem"
                : "Không cho phép khán giả"}
            </div>
          </section>
          <section className="surface waiting-chat-panel">
            <Heading level={3}>Trò chuyện</Heading>
            <GameChat waiting spectator={role === "spectator"} />
          </section>
        </aside>
      </div>
      <Modal
        isOpen={!!confirm}
        onClose={() => setConfirm(null)}
        title={
          confirm === "kick"
            ? "Đuổi người chơi khỏi phòng?"
            : "Rời khỏi phòng chờ?"
        }
        size="small"
        footer={
          <>
            <Button variant="neutral" onClick={() => setConfirm(null)}>
              Ở lại
            </Button>
            <Button
              onClick={() => {
                setConfirm(null)
                void leaveRoom()
              }}
            >
              {confirm === "kick" ? "Đuổi người chơi" : "Rời phòng"}
            </Button>
          </>
        }
      >
        <div className="muted">
          {confirm === "kick"
            ? "Chỗ trống sẽ được mở cho một kỳ hữu khác. Bạn có thể gửi lại lời mời bất cứ lúc nào."
            : "Bạn có thể quay lại sảnh để tìm một bàn cờ khác."}
        </div>
      </Modal>
    </div>
  )
}

type Outcome = {
  result: "win" | "draw" | "loss"
  reason: string
  cause: "checkmate" | "other"
}

function MoveList({
  moves,
  current,
  onSelect,
}: {
  moves: ChessMove[]
  current?: number
  onSelect?: (index: number) => void
}) {
  if (!moves.length)
    return (
      <div className="moves-empty">
        <Swords size={28} strokeWidth={1.4} />
        <div>Ván cờ bắt đầu từ một nước đi.</div>
        <span className="small muted">
          Lịch sử nước đi sẽ xuất hiện tại đây.
        </span>
      </div>
    )
  return (
    <div className="move-list">
      <div className="move-list-labels">
        <span>#</span>
        <span>Đỏ</span>
        <span>Đen</span>
      </div>
      {Array.from({ length: Math.ceil(moves.length / 2) }, (_, i) => (
        <div className="move-row" key={i}>
          <span>{i + 1}.</span>
          {[i * 2, i * 2 + 1].map((n) => (
            <Button
              variant="subtle"
              size="small"
              disabled={!moves[n]}
              key={n}
              className={`${current === n + 1 ? "move-current" : ""} ${
                moves[n]?.side === "red" ? "red-move" : ""
              }`}
              onClick={() => onSelect?.(n + 1)}
            >
              {moves[n]?.notation || "—"}
            </Button>
          ))}
        </div>
      ))}
    </div>
  )
}

export function Game() {
  const { demoElo, applyDemoElo, settings, reducedMotion, playMove, playCue, stopSound } = useExperience()
  const {
    gameConfig: config,
    activeRoom,
    username,
    startGame,
    go,
    notify,
    request,
    roomAccess,
    setRoomAccess,
  } = useApp()
  const [pieces, setPieces] = useState(initialPieces)
  const [moves, setMoves] = useState<ChessMove[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [fen, setFen] = useState<string | null>(null)
  const [turn, setTurn] = useState<Side>("red")
  const seconds = 60
  const [redTimeMs, setRedTimeMs] = useState(activeRoom.seconds * 1000)
  const [blackTimeMs, setBlackTimeMs] = useState(activeRoom.seconds * 1000)
  const [serverPending, setServerPending] = useState(false)
  const roomSocket = useRef<WebSocket | null>(null)
  const [hint, setHint] = useState<{
    x: number
    y: number
  } | null>(null)
  const [confirm, setConfirm] =
    useState<"draw" | "resign" | "leave" | "restart" | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [finisherVisible, setFinisherVisible] = useState(false)
  const [rating, setRating] = useState({ before: demoElo, after: demoElo, delta: 0 })
  const ended = useRef(false)
  useEffect(() => {
    ended.current = false
    return () => {
      // Ignore delayed demo results after this game has unmounted.
      ended.current = true
      stopSound()
    }
  }, [])
  const [resultOpen, setResultOpen] = useState(false)
  const [check, setCheck] = useState(false)
  const [disconnected, setDisconnected] = useState(false)
  const [reconnectSeconds, setReconnectSeconds] = useState(60)
  const [flipped, setFlipped] = useState(config.side === "black")
  useEffect(() => {
    setFlipped(config.side === "black")
  }, [config.side])
  const ai = config.mode === "ai"
  const spectator = !!config.spectator
  const opponentSide = config.side === "red" ? "black" : "red"
  const playerName = spectator
    ? config.side === "red" ? activeRoom.host : "ThanhPhong"
    : username
  const opponentName = ai
    ? "Kỳ Tiên Hội AI"
    : config.side === "black" ? activeRoom.host : "ThanhPhong"
  const winnerSide = !outcome || outcome.result === "draw"
    ? null
    : outcome.result === "win" ? config.side : opponentSide
  const winnerName = outcome?.result === "win" ? playerName : opponentName
  const resultTitle = spectator
    ? "Ván đấu kết thúc"
    : outcome?.result === "win"
      ? "Bạn đã chiến thắng!"
      : outcome?.result === "draw"
        ? "Ván cờ hòa!"
        : "Ván đấu kết thúc — bạn đã thua."
  const resultSummary = winnerSide
    ? `${winnerName} (quân ${winnerSide === "red" ? "Đỏ" : "Đen"}) thắng · ${winnerSide === "red" ? "1–0" : "0–1"}`
    : "Hai kỳ thủ hòa nhau · ½–½"
  const finish = (result: Outcome["result"], reason: string, cause: Outcome["cause"] = "other") => {
    if (ended.current) return
    ended.current = true
    stopSound()
    const change = ai || spectator || config.mode === "online" ? 0 : result === "win" ? 16 : result === "loss" ? -12 : 0
    const after = Math.max(0, Math.min(9999, demoElo + change))
    setRating({ before: demoElo, after, delta: after - demoElo })
    if (change) applyDemoElo(after - demoElo)
    setOutcome({ result, reason, cause })
    const animate = cause === "checkmate" && settings.effects && !reducedMotion
    setFinisherVisible(animate)
    setResultOpen(!animate)
    if (cause === "checkmate") playCue("mate")
    setDisconnected(false)
    setCheck(false)
    setSelected(null)
  }
  useEffect(() => {
    if (!finisherVisible) return
    if (reducedMotion || !settings.effects) {
      setFinisherVisible(false)
      setResultOpen(true)
      stopSound()
      return
    }
    const timer = setTimeout(() => { setFinisherVisible(false); setResultOpen(true) }, 1800)
    return () => clearTimeout(timer)
  }, [finisherVisible, reducedMotion, settings.effects])
  function skipFinisher() {
    setFinisherVisible(false)
    stopSound()
    setResultOpen(true)
  }
  function syncFen(nextFen: string) {
    const nextPieces = piecesFromFen(nextFen)
    setFen(nextFen)
    setPieces(nextPieces)
    const nextSide = nextFen.trim().split(/\s+/)[1] === "b" ? "black" : "red"
    setTurn(nextSide)
    setSelected(null)
    setHint(null)
  }
  function syncGame(game: {
    fen: string
    side_to_move: "w" | "b"
    red_time_ms?: number
    black_time_ms?: number
    paused?: boolean
    status?: string
    winner?: "w" | "b" | null
    reason?: string | null
  }) {
    syncFen(game.fen)
    if (typeof game.red_time_ms === "number") setRedTimeMs(game.red_time_ms)
    if (typeof game.black_time_ms === "number") setBlackTimeMs(game.black_time_ms)
    setTurn(game.side_to_move === "w" ? "red" : "black")
    if (typeof game.paused === "boolean") setDisconnected(game.paused)
    if (game.status === "finished") {
      const playerWon = game.winner === (config.side === "red" ? "w" : "b")
      finish(game.winner ? (playerWon ? "win" : "loss") : "draw", game.reason || "Ván đấu đã kết thúc.")
    }
  }
  function appendMove(side: Side, fromX: number, fromY: number, toX: number, toY: number) {
    setMoves((list) => [
      ...list,
      {
        pieceId: `${side}-${fromX}-${fromY}`,
        fromX,
        fromY,
        toX,
        toY,
        notation: `${side === "red" ? "Đỏ" : "Đen"} ${fromX + 1},${fromY + 1}`,
        side,
      },
    ])
  }
  function settlePve(status: string, winner: "w" | "b" | null | undefined) {
    if (["active", "check"].includes(status)) return
    const playerWon = winner === (config.side === "red" ? "w" : "b")
    finish(winner ? (playerWon ? "win" : "loss") : "draw", status === "checkmate" ? "Chiếu bí" : status === "stalemate" ? "Hết nước đi" : "Ván cờ hòa", status === "checkmate" ? "checkmate" : "other")
  }
  async function requestAiMove(currentFen: string) {
    const response = await request<{
      fen: string
      move: { from: [number, number]; to: [number, number] }
      status?: string
      winner?: "w" | "b" | null
    }>(
      "pve.ai_move",
      {
        fen: currentFen,
        player_side: config.side === "red" ? "w" : "b",
        difficulty: config.difficulty,
      },
      120_000,
    )
    appendMove("black" === config.side ? "red" : "black", response.move.from[1], response.move.from[0], response.move.to[1], response.move.to[0])
    syncFen(response.fen)
    if (response.status) settlePve(response.status, response.winner)
  }
  useEffect(() => {
    if (!ai) return
    let cancelled = false
    setServerPending(true)
    setOutcome(null)
    ended.current = false
    void request<{
      fen: string
      side_to_move: "w" | "b"
      player_side: "w" | "b"
    }>("pve.start", {
      player_side: config.side === "red" ? "w" : "b",
      difficulty: config.difficulty,
    }).then(async (game) => {
      if (cancelled) return
      setMoves([])
      syncFen(game.fen)
      if (game.side_to_move !== game.player_side) await requestAiMove(game.fen)
    }).catch((error) => {
      if (!cancelled) notify(error instanceof Error ? error.message : "Không thể bắt đầu ván với máy.", "error")
    }).finally(() => {
      if (!cancelled) setServerPending(false)
    })
    return () => { cancelled = true }
  }, [config.key])
  useEffect(() => {
    if (ai || !roomAccess) return
    const access = roomAccess
    let cancelled = false
    let socket: WebSocket | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    function connect() {
      const query = new URLSearchParams({ participant_token: access.participant_token })
      socket = new WebSocket(websocketUrl(`/api/v1/rooms/${access.id}/ws?${query.toString()}`))
      roomSocket.current = socket
      socket.onopen = () => {
        attempt = 0
        setDisconnected(false)
      }
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as {
            type?: string
            game?: { fen: string; side_to_move: "w" | "b"; red_time_ms?: number; black_time_ms?: number; paused?: boolean; status?: string; winner?: "w" | "b" | null; reason?: string | null }
            move?: { from: [number, number]; to: [number, number] }
            red_time_ms?: number
            black_time_ms?: number
            side_to_move?: "w" | "b"
            reconnect_seconds?: number
            reason?: string
          }
          if (event.type === "room.snapshot" && event.game) syncGame(event.game)
          else if (event.type === "move_made" && event.game) {
            setServerPending(false)
            if (event.move) {
              const movingSide = event.game.side_to_move === "w" ? "black" : "red"
              appendMove(movingSide, event.move.from[1], event.move.from[0], event.move.to[1], event.move.to[0])
            }
            syncGame(event.game)
          } else if (event.type === "timer_tick") {
            if (typeof event.red_time_ms === "number") setRedTimeMs(event.red_time_ms)
            if (typeof event.black_time_ms === "number") setBlackTimeMs(event.black_time_ms)
            if (event.side_to_move) setTurn(event.side_to_move === "w" ? "red" : "black")
          } else if (["game.timeout", "game.forfeit", "game_over"].includes(event.type || "") && event.game) {
            setServerPending(false)
            syncGame(event.game)
          } else if (event.type === "player.disconnected") {
            setDisconnected(true)
            setReconnectSeconds(event.reconnect_seconds || 60)
          } else if (event.type === "player.reconnected") {
            setDisconnected(false)
            if (event.game) syncGame(event.game)
          } else if (event.type === "room.closed") {
            notify("Phòng đã đóng.", "info")
            setRoomAccess(null)
            go("rooms")
          } else if (event.type === "move_rejected" || event.type === "error") {
            setServerPending(false)
            notify(event.reason || "Máy chủ từ chối nước đi.", "error")
          } else if (event.type === "draw_offered") {
            const accept = window.confirm("Đối thủ muốn hòa ván cờ. Bạn có đồng ý không?")
            socket?.send(JSON.stringify({ type: "respond_draw", accept }))
          } else if (event.type === "draw_declined") {
            notify("Đối thủ đã từ chối hòa.", "info")
          }
        } catch {
          notify("Không đọc được sự kiện từ máy chủ trận đấu.", "error")
        }
      }
      socket.onclose = (event) => {
        if (cancelled || ended.current) return
        if ([4401, 4403, 4404, 4409].includes(event.code)) {
          setRoomAccess(null)
          notify(event.reason || "Phiên phòng đã hết hiệu lực.", "error")
          go("rooms")
          return
        }
        setDisconnected(true)
        retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000))
      }
    }
    const connectTimer = setTimeout(connect, 0)
    return () => {
      cancelled = true
      clearTimeout(connectTimer)
      if (retryTimer) clearTimeout(retryTimer)
      if (roomSocket.current === socket) roomSocket.current = null
      socket?.close(1000, "Game page closed")
    }
  }, [config.key, roomAccess?.id, roomAccess?.participant_token])
  useEffect(() => {
    if (!disconnected || reconnectSeconds <= 0) return
    const timer = setTimeout(() => setReconnectSeconds((n) => n - 1), 1000)
    return () => clearTimeout(timer)
  }, [disconnected, reconnectSeconds])
  async function makePveMove(piece: Piece, x: number, y: number) {
    if (!fen || serverPending) return
    setServerPending(true)
    try {
      const response = await request<{
        fen: string
        status: string
        winner?: "w" | "b" | null
      }>("pve.player_move", {
        fen,
        player_side: config.side === "red" ? "w" : "b",
        from: [piece.y, piece.x],
        to: [y, x],
      })
      appendMove(piece.side, piece.x, piece.y, x, y)
      syncFen(response.fen)
      playMove(piece.label, false)
      if (response.status !== "active" && response.status !== "check") {
        settlePve(response.status, response.winner)
      } else await requestAiMove(response.fen)
    } catch (error) {
      notify(error instanceof Error ? error.message : "Nước đi không hợp lệ.", "error")
    } finally {
      setServerPending(false)
    }
  }
  function makeMove(piece: Piece, x: number, y: number) {
    if (ended.current || serverPending) return
    if (ai) {
      void makePveMove(piece, x, y)
      return
    }
    const socket = roomSocket.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      notify("Đang kết nối lại với máy chủ trận đấu.", "info")
      return
    }
    setServerPending(true)
    socket.send(JSON.stringify({ type: "make_move", from: [piece.y, piece.x], to: [y, x] }))
    setSelected(null)
    setHint(null)
  }
  function square(x: number, y: number) {
    if (outcome || disconnected || turn !== config.side || spectator || serverPending) return
    const piece = pieces.find((p) => p.x === x && p.y === y)
    if (piece?.side === config.side) {
      setSelected(piece.id === selected ? null : piece.id)
      setHint(null)
      return
    }
    const chosen = pieces.find((p) => p.id === selected)
    if (chosen) makeMove(chosen, x, y)
    else notify("Chọn một quân cờ của bạn, rồi chọn vị trí muốn đi.", "info")
  }
  async function leaveOnlineGame() {
    if (!roomAccess) {
      go("rooms")
      return
    }
    try {
      await request("room.leave", {
        room_id: roomAccess.id,
        participant_token: roomAccess.participant_token,
      })
      setRoomAccess(null)
      go("rooms")
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể rời ván đấu.", "error")
    }
  }
  function undo() {
    notify("Nước đi đã được máy chủ xác nhận; không thể sửa lại ván đang chạy.", "info")
  }
  function suggest() {
    const candidate = pieces.find(
      (p) =>
        p.side === config.side &&
        p.label === "Tốt" &&
        !pieces.some(
          (o) => o.x === p.x && o.y === p.y + (config.side === "red" ? -1 : 1),
        ),
    )
    if (candidate) {
      setSelected(candidate.id)
      setHint({
        x: candidate.x,
        y: candidate.y + (config.side === "red" ? -1 : 1),
      })
      notify("Gợi ý: tiến Tốt một bước để mở đường cho quân chủ lực.", "info")
    }
  }
  const remaining = new Map<string, number>()
  pieces.forEach((piece) => {
    const key = `${piece.side}:${piece.label}`
    remaining.set(key, (remaining.get(key) || 0) + 1)
  })
  const captured = initialPieces().filter((piece) => {
    const key = `${piece.side}:${piece.label}`
    const count = remaining.get(key) || 0
    if (count <= 0) return true
    remaining.set(key, count - 1)
    return false
  })
  const clock = formatClock(seconds)
  const last = moves[moves.length - 1]
  const title = ai
    ? `Luyện cờ cùng máy · ${difficultyOptions.find((d) => d.id === config.difficulty)?.name || "Trung bình"}`
    : activeRoom.name
  return (
    <div className="page-stack game-page">
      <ArenaAtmosphere />
      <div className="page-heading-row">
        <div>
          <div className="inline">
            <span className="eyebrow">
              {ai
                ? "CHƠI VỚI MÁY"
                : spectator
                  ? "ĐANG XEM TRẬN ĐẤU"
                  : "VÁN ĐẤU TRỰC TUYẾN"}
            </span>
            <Badge
              label={outcome ? "Đã kết thúc" : "Đang diễn ra"}
              variant={outcome ? "secondary" : "success"}
              className={`game-state-badge ${outcome ? "" : "is-live"}`}
            />
          </div>
          <Heading level={1}>{title}</Heading>
          <div className="small muted mt-xs">
            {ai
              ? "Cứ thử nghiệm. Mỗi nước đi là một bài học."
              : `#${activeRoom.id} · ${activeRoom.seconds} giây / lượt · Đồng hồ máy chủ`}
          </div>
        </div>
        <SoundToggle />
        <Button
          variant="neutral"
          iconStart={<LogOut size={16} />}
          aria-label={ai ? "Thoát ván cờ" : "Thoát phòng"}
          onClick={() => setConfirm("leave")}
        >
          {ai ? "Thoát ván cờ" : "Thoát phòng"}
        </Button>
      </div>
      {disconnected && (
        <div className="reconnection-banner" role="alert">
          <WifiOff size={21} />
          <div className="grow">
            <strong>Đang kết nối lại với máy chủ</strong>
            <div className="small">
              Đồng hồ đã tạm dừng. Máy chủ cho phép kết nối lại trong tối đa 60 giây.
            </div>
          </div>
          <span className="reconnect-timer">{reconnectSeconds}s</span>
        </div>
      )}
      {outcome && (
        <div className="game-ended-banner">
          <Trophy size={20} />
          <span>
            {spectator ? `Ván đấu kết thúc · ${resultSummary}` : "Ván cờ đã kết thúc"}
            {" · "}{outcome.reason}
          </span>
          <Button
            variant="subtle"
            size="small"
            onClick={skipFinisher}
          >
            Xem kết quả
            <ArrowRight size={14} />
          </Button>
        </div>
      )}
      <div className="match-layout">
        <section className="game-board-area">
          <PlayerStrip
            name={opponentName}
            initials={ai ? "AI" : playerInitials(opponentName)}
            elo={ai ? 1200 : 1320}
            side={opponentSide}
            active={turn === opponentSide && !outcome}
            time={ai ? clock : formatClock(Math.ceil((opponentSide === "red" ? redTimeMs : blackTimeMs) / 1000))}
            computer={ai}
            tone="blue"
            winner={outcome?.cause === "checkmate" && outcome.result === "loss"}
          />
          <div className="turn-status">
            <span
              className={`status-dot ${
                turn === config.side ? "your-turn" : "opponent-turn"
              }`}
            />
            <span>
              {outcome
                ? "Ván cờ đã kết thúc"
                : spectator
                  ? "Bạn đang theo dõi ván cờ"
                  : turn === config.side
                    ? "Đến lượt bạn · Chọn một quân để đi"
                    : ai
                      ? "Máy đang suy nghĩ..."
                      : "Chờ nước đi của đối thủ..."}
            </span>
            {check && (
              <span className="check-warning">
                <AlertCircle size={14} />
                Chiếu tướng!
              </span>
            )}
          </div>
          <div
            className={`game-board-wrap ${
              disconnected ? "board-disconnected" : ""
            }`}
          >
            <ChessBoard
              pieces={pieces}
              interactive={!outcome && !spectator}
              onSquare={square}
              selected={selected}
              hint={hint}
              flipped={flipped}
              lastMove={last ? { x: last.toX, y: last.toY } : null}
            />
            {finisherVisible && (
              <CheckmateEffect
                message={resultTitle}
                detail={spectator ? resultSummary : undefined}
                onSkip={skipFinisher}
              />
            )}
          </div>
          <PlayerStrip
            name={playerName}
            initials={playerInitials(playerName)}
            elo={demoElo}
            current={!spectator}
            side={config.side}
            active={turn === config.side && !outcome}
            time={ai ? clock : formatClock(Math.ceil((config.side === "red" ? redTimeMs : blackTimeMs) / 1000))}
            tone="rose"
            winner={outcome?.cause === "checkmate" && outcome.result === "win"}
          />
          <div className="board-action-bar">
            {ai ? (
              <>
                <Button
                  variant="neutral"
                  iconStart={<RotateCcw size={16} />}
                  onClick={undo}
                  disabled={!moves.length || !!outcome}
                >
                  Đi lại
                </Button>
                <Button
                  variant="neutral"
                  iconStart={<Lightbulb size={16} />}
                  onClick={suggest}
                  disabled={!!outcome || turn !== config.side}
                >
                  Gợi ý nước đi
                </Button>
                <Button
                  variant="subtle"
                  iconStart={<RotateCw size={16} />}
                  onClick={() => setConfirm("restart")}
                >
                  Chơi lại
                </Button>
              </>
            ) : !spectator ? (
              <>
                <Button
                  variant="neutral"
                  iconStart={<Handshake size={16} />}
                  disabled={!!outcome}
                  onClick={() => setConfirm("draw")}
                >
                  Cầu hòa
                </Button>
                <Button
                  variant="neutral"
                  iconStart={<Flag size={16} />}
                  disabled={!!outcome}
                  onClick={() => setConfirm("resign")}
                >
                  Đầu hàng
                </Button>
              </>
            ) : (
              <span className="inline muted small">
                <Eye size={16} />
                Chế độ khán giả · Không thể di chuyển quân cờ
              </span>
            )}
            <IconAction
              label="Lật bàn cờ"
              icon={<RotateCw size={18} />}
              onClick={() => setFlipped((v) => !v)}
            />
          </div>
        </section>
        <aside className="match-aside">
          <section className="surface match-info">
            <div className="between">
              <Heading level={3}>Thông tin ván cờ</Heading>
              <Swords size={18} className="muted" />
            </div>
            <div className="match-info-row">
              <span className="muted">Chế độ</span>
              <span>{ai ? "Luyện tập với máy" : "Giao lưu trực tuyến"}</span>
            </div>
            <div className="match-info-row">
              <span className="muted">Nước vừa đi</span>
              <span className={last?.side === "red" ? "red-text" : ""}>
                {last ? last.notation : "Chưa có nước đi"}
              </span>
            </div>
            <div className="match-info-row">
              <span className="muted">Số nước</span>
              <span>{moves.length}</span>
            </div>
            {check && (
              <div className="error-message">
                <AlertCircle size={16} />
                Tướng đang bị chiếu. Hãy hóa giải!
              </div>
            )}
          </section>
          <section className="surface moves-chat-panel">
            <Tabs
              tabs={[
                {
                  id: "moves",
                  label: "Nước đi",
                  content: <MoveList moves={moves} current={moves.length} />,
                },
                ...(!ai
                  ? [
                      {
                        id: "chat",
                        label: "Trò chuyện",
                        content: <GameChat spectator={spectator} />,
                      },
                    ]
                  : []),
              ]}
            />
          </section>
          <section className="surface captured-panel">
            <Heading level={3}>Quân đã bị ăn</Heading>
            <div className="captured-row">
              <span className="piece-dot red" />
              <div className="captured-pieces">
                {captured.filter((p) => p.side === "red").length ? (
                  captured
                    .filter((p) => p.side === "red")
                    .map((p) => (
                      <span className="captured-piece red-text" key={p.id} aria-label={`${p.label} Đỏ đã bị ăn`}>
                        <PieceGlyph side={p.side} type={p.label} />
                      </span>
                    ))
                ) : (
                  <span className="small muted">Chưa mất quân</span>
                )}
              </div>
            </div>
            <div className="captured-row">
              <span className="piece-dot black" />
              <div className="captured-pieces">
                {captured.filter((p) => p.side === "black").length ? (
                  captured
                    .filter((p) => p.side === "black")
                    .map((p) => (
                      <span className="captured-piece" key={p.id} aria-label={`${p.label} Đen đã bị ăn`}>
                        <PieceGlyph side={p.side} type={p.label} />
                      </span>
                    ))
                ) : (
                  <span className="small muted">Chưa mất quân</span>
                )}
              </div>
            </div>
          </section>
        </aside>
      </div>
      <Modal
        isOpen={!!confirm}
        onClose={() => setConfirm(null)}
        title={
          confirm === "resign"
            ? "Bạn muốn đầu hàng?"
            : confirm === "draw"
              ? "Gửi lời cầu hòa?"
              : confirm === "restart"
                ? "Bắt đầu lại ván cờ?"
                : "Rời khỏi ván cờ?"
        }
        size="small"
        footer={
          <>
            <Button variant="neutral" onClick={() => setConfirm(null)}>
              Tiếp tục chơi
            </Button>
            <Button
              onClick={() => {
                const action = confirm
                setConfirm(null)
                if (action === "resign") {
                  if (ai) finish("loss", "Bạn đã đầu hàng.")
                  else roomSocket.current?.send(JSON.stringify({ type: "resign" }))
                }
                else if (action === "draw") {
                  if (ai) notify("Ván luyện tập với máy không hỗ trợ cầu hòa.", "info")
                  else roomSocket.current?.send(JSON.stringify({ type: "offer_draw" }))
                } else if (action === "restart")
                  startGame(config.mode, config.side, config.difficulty)
                else if (ai) go("home")
                else void leaveOnlineGame()
              }}
            >
              {confirm === "resign"
                ? "Đầu hàng"
                : confirm === "draw"
                  ? "Gửi cầu hòa"
                  : confirm === "restart"
                    ? "Chơi lại"
                    : "Rời ván cờ"}
            </Button>
          </>
        }
      >
        <div className="muted">
          {confirm === "draw"
            ? "Lời cầu hòa sẽ được gửi tới đối thủ qua máy chủ."
            : confirm === "restart"
              ? "Tiến trình hiện tại sẽ được xóa. Bạn sẽ bắt đầu lại từ thế cờ khai cuộc."
              : confirm === "resign"
                ? "Ván cờ sẽ kết thúc với kết quả thua. Bạn luôn có thể trở lại và thử sức ở một ván mới."
                : outcome
                  ? "Ván cờ đã kết thúc. Bạn có thể trở về sảnh hoặc bắt đầu một ván mới."
                  : "Rời phòng khi ván chưa kết thúc sẽ được máy chủ tính là đầu hàng."}
        </div>
      </Modal>
      <Modal
        isOpen={resultOpen && !!outcome}
        onClose={() => setResultOpen(false)}
        size="medium"
        className="result-modal"
        title="Kết quả ván cờ"
      >
        <div className={`result-content result-${spectator ? "draw" : outcome?.result}`}>
          <span className="result-icon">
            {outcome?.result === "win" ? (
              <Trophy size={38} strokeWidth={1.5} />
            ) : outcome?.result === "draw" ? (
              <Handshake size={38} strokeWidth={1.5} />
            ) : (
              <Flag size={38} strokeWidth={1.5} />
            )}
          </span>
          <div className="eyebrow">
            {spectator
              ? "KẾT QUẢ VÁN ĐẤU MÔ PHỎNG"
              : outcome?.result === "win"
              ? "MỘT VÁN CỜ THẬT HAY"
              : outcome?.result === "draw"
                ? "KỲ PHÙNG ĐỊCH THỦ"
                : "MỖI VÁN CỜ, MỘT BÀI HỌC"}
          </div>
          <Heading level={1}>
            {resultTitle}
          </Heading>
          {spectator && <div className="player-name">{resultSummary}</div>}
          <div className="muted">{outcome?.reason}</div>
          <div className="result-stats">
            <div>
              <strong>{moves.length}</strong>
              <span>Nước đã đi</span>
            </div>
            <div>
              <strong>
                {spectator
                  ? "Khán giả"
                  : ai ? "Luyện tập"
                  : config.mode === "online" ? "Đấu trực tuyến"
                  : `${rating.delta >= 0 ? "+" : "−"}${Math.abs(rating.delta)} Elo`}
              </strong>
              <span>{ai || spectator || config.mode === "online" ? "Không tính Elo" : "Thay đổi minh họa"}</span>
            </div>
          </div>
          {!ai && !spectator && config.mode !== "online" && <div className="result-cultivation"><div className="small muted">Elo demo: {rating.before.toLocaleString("vi-VN")} → {rating.after.toLocaleString("vi-VN")}</div><RankProgress elo={rating.after} /></div>}
          <Button
            className="button-full"
            iconStart={<RotateCw size={17} />}
            onClick={() =>
              startGame(config.mode, config.side, config.difficulty, spectator)
            }
          >
            {spectator ? "Xem lại ván mẫu" : ai ? "Chơi lại" : "Tái đấu"}
          </Button>
          <Button
            variant="neutral"
            className="button-full"
            onClick={() => go("home")}
          >
            Về sảnh chính
          </Button>
          <span className="small muted">
            {ai ? "Ván luyện tập không thay đổi Elo." : spectator ? "Khán giả không thay đổi Elo." : config.mode === "online" ? "Kết quả nước đi được lưu ở máy chủ." : "Điểm Elo chỉ cập nhật trong phiên demo."}
          </span>
        </div>
      </Modal>
    </div>
  )
}

export function Replay() {
  const { selectedRecord: record, username } = useApp()
  const { demoElo } = useExperience()
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [flipped, setFlipped] = useState(false)
  useEffect(() => {
    if (!playing) return
    if (step >= replayMoves.length) {
      setPlaying(false)
      return
    }
    const timer = setTimeout(() => setStep((n) => n + 1), 900)
    return () => clearTimeout(timer)
  }, [playing, step])
  const pieces = useMemo(() => {
    let position = initialPieces()
    replayMoves.slice(0, step).forEach((move) => {
      position = position
        .filter(
          (p) => p.id === move.pieceId || p.x !== move.toX || p.y !== move.toY,
        )
        .map((p) =>
          p.id === move.pieceId ? { ...p, x: move.toX, y: move.toY } : p,
        )
    })
    return position
  }, [step])
  const last = replayMoves[step - 1]
  return (
    <div className="page-stack replay-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">NHÌN LẠI ĐỂ TIẾN XA HƠN</div>
          <Heading level={1}>Xem lại ván cờ</Heading>
          <div className="muted small mt-xs">
            #{record.id} · {record.date}, {record.time} · {record.duration}
          </div>
        </div>
        <BreadcrumbBack label="Về lịch sử" page="history" />
      </div>
      <div className="match-layout">
        <section className="replay-board-area">
          <PlayerStrip
            name={record.opponent}
            initials={record.initials}
            elo={record.elo}
            side="black"
            tone={record.tone}
            waiting
          />
          <div className="replay-step-label">
            Nước {step} / {replayMoves.length}
            <span>
              {step === 0
                ? "Thế cờ khai cuộc"
                : `${last.side === "red" ? "Đỏ" : "Đen"}: ${last.notation}`}
            </span>
          </div>
          <ChessBoard
            pieces={pieces}
            flipped={flipped}
            lastMove={last ? { x: last.toX, y: last.toY } : null}
          />
          <PlayerStrip
            name={username}
            initials="MA"
            elo={demoElo}
            current
            side="red"
            tone="rose"
            waiting
          />
          <div className="replay-controls">
            <IconAction
              label="Về khai cuộc"
              icon={<ChevronsLeft size={21} />}
              disabled={step === 0}
              onClick={() => {
                setPlaying(false)
                setStep(0)
              }}
            />
            <IconAction
              label="Nước trước"
              icon={<ChevronLeft size={22} />}
              disabled={step === 0}
              onClick={() => {
                setPlaying(false)
                setStep((n) => n - 1)
              }}
            />
            <Button
              className="replay-play-button"
              aria-label={playing ? "Tạm dừng" : "Phát lại tự động"}
              onClick={() => {
                if (step === replayMoves.length) setStep(0)
                setPlaying((v) => !v)
              }}
            >
              {playing ? <Pause size={20} /> : <Play size={20} />}
            </Button>
            <IconAction
              label="Nước tiếp theo"
              icon={<ChevronRight size={22} />}
              disabled={step === replayMoves.length}
              onClick={() => {
                setPlaying(false)
                setStep((n) => n + 1)
              }}
            />
            <IconAction
              label="Đến nước cuối"
              icon={<ChevronsRight size={21} />}
              disabled={step === replayMoves.length}
              onClick={() => {
                setPlaying(false)
                setStep(replayMoves.length)
              }}
            />
            <span className="replay-control-divider" />
            <IconAction
              label="Lật bàn cờ"
              icon={<RotateCw size={19} />}
              onClick={() => setFlipped((v) => !v)}
            />
          </div>
          <div
            className="replay-progress"
            role="progressbar"
            aria-valuenow={step}
            aria-valuemax={replayMoves.length}
            aria-valuemin={0}
            aria-label="Tiến trình xem lại"
          >
            <span style={{ width: `${(step / replayMoves.length) * 100}%` }} />
          </div>
        </section>
        <aside className="match-aside">
          <section className="surface replay-summary">
            <SectionTitle title="Kết quả ván đấu" />
            <span className={`result-tag ${record.result}`}>
              {resultLabels[record.result]}
            </span>
            <Heading className="mt-xs">{record.reason}</Heading>
            <div className="muted small">MinhAnh vs {record.opponent}</div>
            <div className="match-info-row">
              <span className="muted">Thay đổi Elo</span>
              <span
                className={`elo-change ${
                  record.change > 0 ? "positive" : "negative"
                }`}
              >
                {record.change > 0 ? "+" : ""}
                {record.change} Elo
              </span>
            </div>
            <div className="match-info-row">
              <span className="muted">Thời lượng</span>
              <span>{record.duration}</span>
            </div>
          </section>
          <section className="surface replay-moves">
            <SectionTitle title="Biên bản nước đi" />
            <MoveList
              moves={replayMoves}
              current={step}
              onSelect={(n) => {
                setPlaying(false)
                setStep(n)
              }}
            />
            <div className="form-help">
              Bấm vào ký hiệu để xem thế cờ tại nước đó.
            </div>
          </section>
          <section className="replay-tip">
            <Lightbulb size={20} />
            <div>
              <Heading level={3}>Học từ mỗi nước đi</Heading>
              <div className="muted small mt-xs">
                Xem lại những thời điểm quan trọng để tìm ra hướng đi tốt hơn
                cho ván tiếp theo.
              </div>
            </div>
          </section>
          <div className="small muted">
            Biên bản khai cuộc minh họa · 12 nước
          </div>
        </aside>
      </div>
    </div>
  )
}
