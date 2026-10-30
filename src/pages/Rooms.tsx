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
import { DemoMatchmakingNotice } from "../room-demo"

export default function Rooms() {
  const { roomList, openModal, joinRoom, notify } = useApp()
  const [query, setQuery] = useState("")
  const [time, setTime] = useState("all")
  const [code, setCode] = useState("")
  const [status, setStatus] = useState("all")
  const [state, setState] = useState("default")
  const [visible, setVisible] = useState(6)
  useEffect(() => {
    if (state !== "loading") return
    const timer = setTimeout(() => setState("default"), 900)
    return () => clearTimeout(timer)
  }, [state])
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
    const room = roomList.find(
      (r) => r.id.toLowerCase() === code.trim().replace("#", "").toLowerCase(),
    )
    if (room) joinRoom(room)
    else
      notify(
        "Không tìm thấy mã phòng. Hãy kiểm tra lại mã và thử lần nữa.",
        "error",
      )
  }
  return (
    <div className="page-stack rooms-page">
      <ArenaAtmosphere />
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">KẾT NỐI KỲ HỮU</div>
          <Heading level={1}>Sảnh đấu</Heading>
          <div className="muted mt-xs">
            Khám phá phòng mẫu và thử các vai trò trong bản demo.
          </div>
          <DemoMatchmakingNotice />
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
            Các phòng và kỳ thủ bên dưới đều là dữ liệu mô phỏng.
          </div>
        </div>
        <OnlineStatus>1.248 kỳ hữu · số liệu demo</OnlineStatus>
      </div>
      <section className="surface quick-join-panel">
        <div className="inline">
          <span className="quick-icon tone-sand">
            <Users size={22} />
          </span>
          <div>
            <Heading level={3}>Đã có lời mời?</Heading>
            <div className="small muted">Nhập mã để mở một phòng mẫu trong bản demo.</div>
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
            placeholder="Nhập mã phòng, ví dụ KD2846"
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
            <OnlineStatus>Dữ liệu demo</OnlineStatus>
            <Button
              variant="subtle"
              size="small"
              iconStart={
                <RefreshCw
                  size={15}
                  className={state === "loading" ? "animate-spin" : ""}
                />
              }
              onClick={() => setState("loading")}
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
            description="Đây là trạng thái lỗi mô phỏng; không có kết nối máy chủ."
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
            Phòng riêng tư yêu cầu mật khẩu. Phòng đang đấu có thể vào xem.
          </span>
          <div className="prototype-state">
            <span className="small muted">Xem trạng thái:</span>
            <SelectField
              options={[
                { value: "default", label: "Mặc định" },
                { value: "loading", label: "Đang tải" },
                { value: "empty", label: "Sảnh trống" },
                { value: "error", label: "Lỗi tải mẫu (mô phỏng)" },
              ]}
              value={state}
              onChange={setState}
            />
          </div>
        </div>
      </section>
    </div>
  )
}

function SwordsIcon() {
  return <LayoutGrid size={25} strokeWidth={1.5} />
}
