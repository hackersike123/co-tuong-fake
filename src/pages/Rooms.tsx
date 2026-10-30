import { useEffect, useState } from "react"
import { Button, InputField, SelectField } from "@figma/astraui"
import {
  AlertCircle,
  ArrowRight,
  Clock,
  LayoutGrid,
  Plus,
  RefreshCw,
  Search,
  Users,
} from "lucide-react"
import { EmptyState, Heading, OnlineStatus, RoomCard } from "../components"
import { useApp } from "../context"
import { ArenaAtmosphere } from "../experience/effects"
import { websocketUrl } from "../config/connection"
import { playerInitials, type Room } from "../data"

type ServerRoom = {
  id: number
  room_id?: number
  room_name?: string
  name?: string
  host_name?: string
  is_public?: boolean
  allow_spectators?: boolean
  status?: string
  player_count?: number
  timer_seconds?: number
}

function mapRoom(source: ServerRoom): Room {
  const host = source.host_name || "Kỳ hữu"
  return {
    id: String(source.id ?? source.room_id ?? ""),
    name: source.room_name || source.name || "Phòng cờ tướng",
    host,
    initials: playerInitials(host),
    elo: 1200,
    seconds: source.timer_seconds || 30,
    players: source.player_count || 1,
    private: source.is_public === false,
    playing: source.status === "playing",
    spectators: source.allow_spectators !== false,
    tone: "sage",
  }
}

export default function Rooms() {
  const { roomList, setRoomList, openModal, joinRoomByCode, request } = useApp()
  const [query, setQuery] = useState("")
  const [time, setTime] = useState("all")
  const [code, setCode] = useState("")
  const [status, setStatus] = useState("all")
  const [state, setState] = useState("loading")
  const [visible, setVisible] = useState(6)
  useEffect(() => {
    let stopped = false
    let socket: WebSocket | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    function connect() {
      socket = new WebSocket(websocketUrl("/api/v1/rooms/ws"))
      socket.onopen = () => {
        attempt = 0
        if (!stopped) setState("default")
      }
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as {
            type?: string
            rooms?: ServerRoom[]
            room?: ServerRoom
            room_id?: number
          }
          if (event.type === "rooms.snapshot" && Array.isArray(event.rooms)) {
            setRoomList(event.rooms.map(mapRoom))
          } else if ((event.type === "room.created" || event.type === "room.updated") && event.room) {
            const updated = mapRoom(event.room)
            setRoomList((current) => [updated, ...current.filter((room) => room.id !== updated.id)])
          } else if (event.type === "room.removed" && event.room_id) {
            setRoomList((current) => current.filter((room) => room.id !== String(event.room_id)))
          }
        } catch {
          setState("error")
        }
      }
      socket.onerror = () => setState("error")
      socket.onclose = () => {
        if (stopped) return
        setState("error")
        retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000))
      }
    }
    connect()
    return () => {
      stopped = true
      if (retryTimer) clearTimeout(retryTimer)
      socket?.close(1000, "Lobby page closed")
    }
  }, [setRoomList])
  const filtered = roomList.filter(
    (room) =>
      `${room.name} ${room.id} ${room.host}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (time === "all" || String(room.seconds) === time) &&
      (status === "all" ||
        (status === "waiting" ? !room.playing : room.playing)),
  )
  function quickJoin() {
    void joinRoomByCode(code)
  }
  return (
    <div className="page-stack rooms-page">
      <ArenaAtmosphere />
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">KẾT NỐI KỲ HỮU</div>
          <Heading level={1}>Sảnh đấu</Heading>
          <div className="muted mt-xs">
            Tham gia các phòng công khai đang chờ đối thủ.
          </div>
        </div>
        <Button
          iconStart={<Plus size={17} />}
          onClick={() => openModal("create")}
        >
          Tạo phòng mới
        </Button>
      </div>
      <div className="lobby-banner">
        <span className="lobby-banner-icon">
          <SwordsIcon />
        </span>
        <div className="grow">
          <Heading level={3}>Giao lưu, học hỏi, cùng tiến bộ.</Heading>
          <div className="small muted">
            Danh sách được cập nhật trực tiếp qua WebSocket.
          </div>
        </div>
        <OnlineStatus>{state === "default" ? "WebSocket trực tuyến" : "Đang kết nối"}</OnlineStatus>
      </div>
      <section className="surface quick-join-panel">
        <div className="inline">
          <span className="quick-icon tone-sand">
            <Users size={22} />
          </span>
          <div>
            <Heading level={3}>Đã có lời mời?</Heading>
            <div className="small muted">Nhập mã phòng do bạn bè gửi.</div>
          </div>
        </div>
        <form
          className="quick-join-form"
          onSubmit={(e) => {
            e.preventDefault()
            quickJoin()
          }}
        >
          <InputField
            aria-label="Mã phòng"
            placeholder="Nhập mã phòng, ví dụ 42"
            value={code}
            onChange={setCode}
            maxLength={12}
            required
          />
          <Button
            variant="neutral"
            type="submit"
            iconEnd={<ArrowRight size={16} />}
          >
            Vào nhanh
          </Button>
        </form>
      </section>
      <section className="surface rooms-list-panel">
        <div className="section-title">
          <div className="inline">
            <Heading>Phòng công khai</Heading>
            <span className="count-badge">{filtered.length}</span>
          </div>
          <div className="inline">
            <OnlineStatus>{state === "default" ? "Đang cập nhật trực tiếp" : "Mất kết nối"}</OnlineStatus>
            <Button
              variant="subtle"
              size="small"
              iconStart={
                <RefreshCw
                  size={15}
                  className={state === "loading" ? "animate-spin" : ""}
                />
              }
              onClick={async () => {
                setState("loading")
                try {
                  const rooms = await request<ServerRoom[]>("room.list")
                  setRoomList(rooms.map(mapRoom))
                  setState("default")
                } catch {
                  setState("error")
                }
              }}
            >
              Làm mới
            </Button>
          </div>
        </div>
        <div className="room-filters">
          <div className="room-search">
            <InputField
              prefix={<Search size={17} />}
              placeholder="Tìm tên phòng, kỳ thủ hoặc mã phòng..."
              aria-label="Tìm phòng"
              value={query}
              onChange={setQuery}
            />
          </div>
          <div className="time-filters">
            {[
              { value: "all", label: "Tất cả" },
              { value: "15", label: "15s" },
              { value: "30", label: "30s" },
              { value: "60", label: "60s" },
            ].map((option) => (
              <Button
                key={option.value}
                variant="subtle"
                size="small"
                className={`filter-chip ${
                  time === option.value ? "active" : ""
                }`}
                onClick={() => {
                  setTime(option.value)
                  setVisible(6)
                }}
              >
                {option.value !== "all" && <Clock size={13} />}
                {option.label}
              </Button>
            ))}
          </div>
          <SelectField
            options={[
              { value: "all", label: "Mọi trạng thái" },
              { value: "waiting", label: "Đang chờ" },
              { value: "playing", label: "Đang đấu" },
            ]}
            value={status}
            onChange={setStatus}
          />
        </div>
        {state === "loading" ? (
          <div
            className="room-grid"
            aria-busy="true"
            aria-label="Đang tải danh sách phòng"
          >
            {Array.from({ length: 6 }, (_, i) => (
              <div className="room-skeleton" key={i}>
                <div />
                <div />
                <div />
                <div />
              </div>
            ))}
          </div>
        ) : state === "error" ? (
          <EmptyState
            icon={<AlertCircle size={28} />}
            title="Chưa thể tải danh sách phòng"
            description="Không thể kết nối tới sảnh WebSocket. Hệ thống sẽ tự thử lại."
            action="Thử lại"
            onAction={() => setState("loading")}
          />
        ) : state === "empty" || filtered.length === 0 ? (
          <EmptyState
            icon={<LayoutGrid size={28} />}
            title={query ? "Chưa tìm thấy phòng phù hợp" : "Sảnh đang yên tĩnh"}
            description={
              query
                ? "Thử từ khóa khác hoặc bỏ bớt bộ lọc. Một bàn cờ phù hợp đang chờ bạn."
                : "Hãy là người khai cuộc đầu tiên. Tạo phòng và mời kỳ hữu cùng chơi."
            }
            action={query ? "Xóa bộ lọc" : "Tạo phòng đầu tiên"}
            onAction={() => {
              if (query) {
                setQuery("")
                setTime("all")
                setStatus("all")
                setState("default")
              } else openModal("create")
            }}
          />
        ) : (
          <>
            <div className="room-grid">
              {filtered.slice(0, visible).map((room) => (
                <RoomCard key={room.id} room={room} />
              ))}
            </div>
            {filtered.length > visible && (
              <div className="load-more">
                <Button
                  variant="neutral"
                  onClick={() => setVisible((n) => n + 6)}
                >
                  Xem thêm phòng
                </Button>
              </div>
            )}
          </>
        )}
        <div className="list-panel-footer">
          <span className="small muted">
            Phòng riêng tư cần mật khẩu hoặc liên kết mời.
          </span>
        </div>
      </section>
    </div>
  )
}

function SwordsIcon() {
  return <LayoutGrid size={25} strokeWidth={1.5} />
}
