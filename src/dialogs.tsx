import { useState } from "react"
import { Button, InputField, SelectField, SwitchField } from "@figma/astraui"
import {
  AlertCircle,
  ArrowRight,
  Clock,
  Copy,
  Eye,
  Globe,
  Link,
  Loader2,
  Lock,
  Mail,
  MessageCircle,
  Plus,
  Send,
  ShieldCheck,
  Users,
  Volume2,
} from "lucide-react"
import { Dialog as Modal, Heading, IconAction, PieceGlyph, UserAvatar } from "./components"
import { useApp, type ModalName, type RoomAccess } from "./context"
import { playerInitials, type Room } from "./data"
import { ProfileEditor } from "./experience/ProfileEditor"
import { useExperience, type MotionPreference } from "./experience/Experience"
import type { AudioCue } from "./experience/audio"
import { CULTIVATION_LAYERS, CULTIVATION_RANKS, getCultivationRank } from "./ranks"
import { RankBadge } from "./rank-ui"
import { SettingSwitch } from "./experience/SettingSwitch"

export function GlobalDialogs({
  modal,
  onClose,
}: {
  modal: ModalName
  onClose: () => void
}) {
  if (modal === "create") return <CreateRoomDialog onClose={onClose} />
  if (modal === "password") return <PasswordDialog onClose={onClose} />
  if (modal === "share") return <ShareDialog onClose={onClose} />
  if (modal === "rules") return <RulesDialog onClose={onClose} />
  if (modal === "tips") return <TipsDialog onClose={onClose} />
  if (modal === "settings") return <SettingsDialog onClose={onClose} />
  if (modal === "edit") return <ProfileEditor onClose={onClose} />
  if (modal === "ranks") return <RankGuide onClose={onClose} />
  return null
}

function CreateRoomDialog({ onClose }: { onClose: () => void }) {
  const { demoElo } = useExperience()
  const { username, profileTone, setRoomList, setActiveRoom, setRoomAccess, setIsHost, request, go, notify } =
    useApp()
  const [name, setName] = useState("")
  const [seconds, setSeconds] = useState(30)
  const [privacy, setPrivacy] = useState("public")
  const [password, setPassword] = useState("")
  const [spectators, setSpectators] = useState(true)
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  async function create(e: React.FormEvent) {
    e.preventDefault()
    if (name.trim().length < 3) {
      setError("Tên phòng cần có ít nhất 3 ký tự.")
      return
    }
    if (privacy === "private" && password.length < 4) {
      setError("Mật khẩu phòng cần có ít nhất 4 ký tự.")
      return
    }
    setError("")
    setPending(true)
    try {
      const access = await request<RoomAccess>("room.create", {
        room_name: name.trim(),
        host_name: username,
        time_per_move: seconds,
        is_public: privacy === "public",
        password: privacy === "private" ? password : undefined,
        allow_spectators: spectators,
      })
      const room: Room = {
        id: String(access.id),
        name: access.room_name,
        host: access.host_name,
        ownedByMe: true,
        initials: playerInitials(access.host_name),
        elo: demoElo,
        seconds: access.timer_seconds,
        players: access.player_count,
        private: !access.is_public,
        spectators: access.allow_spectators,
        tone: profileTone,
      }
      setRoomList((list) => [room, ...list])
      setActiveRoom(room)
      setRoomAccess(access)
      setIsHost(true)
      go("waiting")
      notify(`Đã tạo phòng ${room.id}.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tạo phòng.")
    } finally {
      setPending(false)
    }
  }
  return (
    <Modal isOpen onClose={onClose} title="Tạo một bàn cờ mới" size="medium">
      <div className="modal-intro">
        Một không gian riêng để gặp gỡ và giao lưu cùng kỳ hữu.
      </div>
      <form className="form-stack" onSubmit={create} noValidate>
        <InputField
          label="Tên phòng"
          aria-label="Tên phòng"
          placeholder={`Ví dụ: Bàn cờ của ${username}`}
          value={name}
          onChange={setName}
          maxLength={50}
          autoFocus
          required
        />
        <div>
          <div className="form-label inline">
            <Clock size={16} />
            Thời gian mỗi lượt
          </div>
          <div className="choice-row">
            {[15, 30, 60].map((time) => (
              <Button
                type="button"
                variant="neutral"
                className={`choice-button ${seconds === time ? "chosen" : ""}`}
                key={time}
                onClick={() => setSeconds(time)}
              >
                {time} giây
              </Button>
            ))}
          </div>
          <div className="form-help mt-xs">
            {seconds === 15
              ? "Cờ nhanh, thử thách phản xạ."
              : seconds === 30
                ? "Cân bằng giữa tốc độ và tính toán."
                : "Thêm thời gian cho những nước cờ sâu."}
          </div>
        </div>
        <div>
          <div className="form-label">Ai có thể tham gia?</div>
          <div className="choice-row two">
            {[
              { value: "public", label: "Công khai", icon: Globe },
              { value: "private", label: "Riêng tư", icon: Lock },
            ].map(({ value, label, icon: Icon }) => (
              <Button
                type="button"
                variant="neutral"
                className={`choice-button ${privacy === value ? "chosen" : ""}`}
                key={value}
                iconStart={<Icon size={16} />}
                onClick={() => setPrivacy(value)}
              >
                {label}
              </Button>
            ))}
          </div>
        </div>
        {privacy === "private" && (
          <InputField
            label="Mật khẩu phòng"
            aria-label="Mật khẩu phòng"
            placeholder="Ít nhất 4 ký tự"
            type="password"
            value={password}
            onChange={setPassword}
            prefix={<Lock size={16} />}
            autoComplete="new-password"
            required
          />
        )}
        <div className="switch-setting">
          <span className="setting-icon">
            <Eye size={20} />
          </span>
          <SwitchField
            label="Cho phép khán giả"
            description="Kỳ hữu có thể vào xem và trò chuyện."
            defaultSelected
            onChange={setSpectators}
          />
        </div>
        {error && (
          <div className="error-message" role="alert">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <div className="form-actions">
          <Button type="button" variant="neutral" onClick={onClose}>
            Để sau
          </Button>
          <Button
            type="submit"
            disabled={pending}
            iconStart={
              pending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Plus size={16} />
              )
            }
          >
            {pending ? "Đang tạo phòng..." : "Tạo phòng"}
          </Button>
        </div>
          <div className="form-help">Bạn là chủ phòng, cầm quân Đỏ và đi trước.</div>
      </form>
    </Modal>
  )
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const { activeRoom, joinRoomWithPassword } = useApp()
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  return (
    <Modal isOpen onClose={onClose} title="Bàn cờ dành cho kỳ hữu" size="small">
      <div className="private-room-icon">
        <Lock size={27} />
      </div>
      <Heading level={3}>{activeRoom.name}</Heading>
      <div className="muted small mt-xs">#{activeRoom.id} · Phòng riêng tư</div>
      <div className="modal-intro mt-xs">
        Nhập mật khẩu được chủ phòng chia sẻ để tham gia.
      </div>
      <form
        className="form-stack"
        onSubmit={async (e) => {
          e.preventDefault()
          if (password.length < 4) {
            setError("Mật khẩu cần có ít nhất 4 ký tự. Vui lòng thử lại.")
            return
          }
          setPending(true)
          setError("")
          try {
            await joinRoomWithPassword(password)
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Không thể vào phòng.")
          } finally {
            setPending(false)
          }
        }}
      >
        <InputField
          autoFocus
          label="Mật khẩu phòng"
          aria-label="Mật khẩu phòng"
          prefix={<Lock size={16} />}
          value={password}
          onChange={setPassword}
          placeholder="Nhập mật khẩu"
          type="password"
          autoComplete="off"
        />
        {error && (
          <div className="error-message" role="alert">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <Button
          type="submit"
          disabled={pending}
          iconEnd={
            pending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <ArrowRight size={16} />
            )
          }
        >
          {pending ? "Đang vào phòng..." : "Vào phòng"}
        </Button>
        <div className="small muted">Mật khẩu được xác thực bởi máy chủ.</div>
      </form>
    </Modal>
  )
}

function ShareDialog({ onClose }: { onClose: () => void }) {
  const { activeRoom, roomAccess, request, notify } = useApp()
  const [inviteEmail, setInviteEmail] = useState("")
  const [emailPending, setEmailPending] = useState(false)
  const [emailError, setEmailError] = useState("")
  const link = roomAccess?.join_url || `${window.location.origin}/room/${activeRoom.id}`
  async function sendEmailInvite() {
    if (!roomAccess || !inviteEmail.trim()) return
    setEmailPending(true)
    setEmailError("")
    try {
      await request("room.invite", {
        room_id: roomAccess.id,
        participant_token: roomAccess.participant_token,
        email: inviteEmail.trim(),
      })
      notify(`Đã gửi lời mời tới ${inviteEmail.trim()}.`)
      setInviteEmail("")
    } catch (error) {
      setEmailError(error instanceof Error ? error.message : "Không gửi được thư mời.")
    } finally {
      setEmailPending(false)
    }
  }
  async function copy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value)
      notify(label)
    } catch {
      notify(
        "Trình duyệt chưa cho phép sao chép. Hãy chọn nội dung và sao chép thủ công.",
        "info",
      )
    }
  }
  async function share(channel: string) {
    if (channel === "Facebook")
      window.open(
        `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(link)}`,
        "_blank",
        "noopener,noreferrer",
      )
    else if (channel === "Telegram")
      window.open(
        `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(`Cùng chơi cờ tướng tại ${activeRoom.name}!`)}`,
        "_blank",
        "noopener,noreferrer",
      )
    else if (channel === "Email")
      window.location.href = `mailto:?subject=${encodeURIComponent("Mời bạn một ván cờ trên Kỳ Tiên Hội")}&body=${encodeURIComponent(`Cùng giao lưu tại phòng ${activeRoom.name}.\nMã phòng: ${activeRoom.id}\n${link}`)}`
    else {
      if (navigator.share) {
        try {
          await navigator.share({
            title: "Cùng khai cuộc trên Kỳ Tiên Hội",
            text: `Mời bạn vào phòng ${activeRoom.id}`,
            url: link,
          })
        } catch {
          /* The native share dialog can be dismissed. */
        }
      } else
        await copy(link, `Đã sao chép lời mời. Bạn có thể dán vào ${channel}.`)
    }
  }
  return (
    <Modal
      isOpen
      onClose={onClose}
      title="Một ván cờ, thêm một người bạn"
      size="medium"
    >
      <div className="modal-intro">
        Gửi lời mời và cùng kỳ hữu tận hưởng một ván cờ hay.
      </div>
      <div className="share-room-heading">
        <span className="quick-icon tone-sage">
          <Users size={23} />
        </span>
        <div>
          <Heading level={3}>{activeRoom.name}</Heading>
          <span className="small muted">
            {activeRoom.seconds} giây / lượt ·{" "}
            {activeRoom.private ? "Riêng tư" : "Công khai"}
          </span>
        </div>
      </div>
      <div className="share-code-area">
        <span className="small muted">MÃ PHÒNG</span>
        <div className="between">
          <span className="share-big-code">{activeRoom.id}</span>
          <Button
            variant="neutral"
            size="small"
            iconStart={<Copy size={15} />}
            onClick={() => copy(activeRoom.id, "Đã sao chép mã phòng.")}
          >
            Sao chép mã
          </Button>
        </div>
      </div>
      <InputField
        label="Liên kết mời"
        aria-label="Liên kết mời"
        value={link}
        readOnly
        prefix={<Link size={16} />}
        suffix={
          <IconAction
            label="Sao chép liên kết"
            icon={<Copy size={16} />}
            onClick={() => copy(link, "Đã sao chép liên kết mời.")}
          />
        }
      />
      <div className="email-invite-row">
        <InputField
          label="Gửi lời mời qua email"
          aria-label="Email bạn bè"
          type="email"
          value={inviteEmail}
          onChange={setInviteEmail}
          placeholder="ban@example.com"
          autoComplete="email"
        />
        <Button
          variant="neutral"
          disabled={!inviteEmail.trim() || emailPending || roomAccess?.role !== "player1"}
          onClick={() => void sendEmailInvite()}
        >
          {emailPending ? "Đang gửi..." : "Gửi thư mời"}
        </Button>
      </div>
      {emailError && <div className="error-message" role="alert">{emailError}</div>}
      <div className="share-options">
        {[
          { name: "Facebook", text: "f", tone: "blue" },
          { name: "Messenger", icon: MessageCircle, tone: "blue" },
          { name: "Zalo", text: "Z", tone: "blue" },
          { name: "Telegram", icon: Send, tone: "blue" },
          { name: "Email", icon: Mail, tone: "sand" },
        ].map(({ name, icon: Icon, text, tone }) => (
          <Button
            variant="subtle"
            className="share-option"
            key={name}
            onClick={() => share(name)}
          >
            <span className={`share-channel-icon tone-${tone}`}>
              {Icon ? <Icon size={23} /> : text}
            </span>
            <span>{name}</span>
          </Button>
        ))}
      </div>
      <div className="info-message">
        <ShieldCheck size={16} />
        Chỉ chia sẻ mật khẩu phòng riêng với những người bạn tin tưởng.
      </div>
    </Modal>
  )
}

function RulesDialog({ onClose }: { onClose: () => void }) {
  const { go } = useApp()
  return (
    <Modal isOpen onClose={onClose} title="Luật cờ tướng" size="large">
      <div className="modal-intro">
        Cờ tướng không khó bắt đầu. Cùng làm quen những điều cơ bản.
      </div>
      <div className="rules-intro">
        <span className="choice-piece red"><PieceGlyph side="red" type="Tướng" /></span>
        <div>
          <Heading level={3}>Mục tiêu: chiếu bí Tướng đối phương</Heading>
          <div className="small muted">
            Mỗi bên có 16 quân trên bàn 9 cột × 10 hàng. Quân Đỏ đi trước, hai
            bên lần lượt đi một nước.
          </div>
        </div>
      </div>
      <div className="rules-grid">
        {([
          {
            name: "Tướng",
            text: "Đi 1 ô ngang hoặc dọc, luôn ở trong cung 3 × 3.",
          },
          {
            name: "Sĩ",
            text: "Đi chéo 1 ô trong cung để bảo vệ Tướng.",
          },
          {
            name: "Tượng",
            text: "Đi chéo 2 ô, không qua sông, không nhảy qua quân cản.",
          },
          {
            name: "Xe",
            text: "Đi ngang hoặc dọc bao nhiêu ô tùy ý, không nhảy quân.",
          },
          {
            name: "Mã",
            text: "Đi 2 ô thẳng và 1 ô ngang, có thể bị cản chân.",
          },
          {
            name: "Pháo",
            text: "Đi như Xe. Khi ăn quân phải nhảy qua đúng 1 quân.",
          },
          {
            name: "Tốt",
            text: "Tiến 1 ô; qua sông có thể đi ngang, không được lùi.",
          },
        ] as const).map((rule) => (
          <div className="rule-item" key={rule.name}>
            <span className="rule-piece"><PieceGlyph side="red" type={rule.name} /></span>
            <div>
              <div className="player-name">{rule.name}</div>
              <div className="small muted">{rule.text}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="info-message">
        <AlertCircle size={17} />
        <span>
          Không để hai Tướng nhìn thẳng nhau mà không có quân cản. Khi bị chiếu,
          bạn cần hóa giải ngay trong nước kế tiếp.
        </span>
      </div>
      <div className="rules-prototype-note">
        <ShieldCheck size={17} />
        <span>
          Nước đi PvP và PvE được máy chủ kiểm tra bằng bộ luật cờ tướng trước
          khi cập nhật trạng thái bàn cờ.
        </span>
      </div>
      <div className="form-actions">
        <Button variant="neutral" onClick={onClose}>
          Đã hiểu
        </Button>
        <Button onClick={() => go("ai")} iconEnd={<ArrowRight size={16} />}>
          Thử một ván với máy
        </Button>
      </div>
    </Modal>
  )
}

function TipsDialog({ onClose }: { onClose: () => void }) {
  const { go, openModal } = useApp()
  const tips = [
    {
      title: "Nhìn nguy cơ trước khi đi",
      text: "Tự hỏi đối phương đang dọa chiếu hay ăn quân nào. Hóa giải nguy cơ trước khi thực hiện kế hoạch của mình.",
    },
    {
      title: "Triển khai quân chủ lực sớm",
      text: "Đưa Mã, Xe và Pháo ra vị trí có thể phối hợp. Tránh đi đi lại lại một quân trong khai cuộc nếu không có mục đích rõ ràng.",
    },
    {
      title: "Giữ Tướng an toàn",
      text: "Đừng bỏ trống trung lộ hoặc vội phá thế phòng thủ của Sĩ, Tượng. Luôn kiểm tra đường chiếu sau nước đi dự định.",
    },
    {
      title: "Phối hợp trước khi tấn công",
      text: "Cho hai quân cùng hỗ trợ một mục tiêu. Một Xe hoặc Pháo đơn độc dễ bị đuổi và làm bạn mất nhịp.",
    },
    {
      title: "Đừng chỉ nhìn quân có thể ăn",
      text: "Tính thêm nước đáp trả của đối phương. Ăn được một Tốt chưa chắc tốt nếu mất quân mạnh hoặc để Tướng bị uy hiếp.",
    },
    {
      title: "Học từ một tình huống sau ván",
      text: "Xem lại nước khiến bạn mất quân hoặc mất thế. Ghi nhớ một điều cần tránh ở ván sau, thay vì chỉ nhìn kết quả thắng thua.",
    },
  ]
  return (
    <Modal
      isOpen
      onClose={onClose}
      title="Mẹo chơi cho người mới"
      size="large"
      footer={
        <>
          <Button variant="neutral" onClick={() => openModal("rules")}>
            Luật cờ tướng
          </Button>
          <Button onClick={() => go("ai")} iconEnd={<ArrowRight size={16} />}>
            Luyện tập với máy
          </Button>
        </>
      }
    >
      <div className="modal-intro">
        Một vài thói quen nhỏ để khai cuộc vững vàng và bớt bỏ sót nước đi.
      </div>
      <div className="rules-grid">
        {tips.map((tip, index) => (
          <div className="rule-item" key={tip.title}>
            <span className="quick-icon tone-sage" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <Heading level={3}>{tip.title}</Heading>
              <div className="small muted mt-xs">{tip.text}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="info-message">
        <ShieldCheck size={17} />
        <span>
          Đây là gợi ý chiến thuật, không phải nước đi bắt buộc. Máy chủ kiểm
          tra luật cờ khi xác nhận từng nước đi.
        </span>
      </div>
    </Modal>
  )
}

function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { notify } = useApp()
  const { settings, updateSettings, soundEnabled, audioPending, audioError, toggleSound, playCue, systemReducedMotion, storageError } = useExperience()
  const [sample, setSample] = useState<AudioCue>("Tướng")
  return (
    <Modal
      isOpen
      onClose={onClose}
      title="Âm thanh và linh khí"
      size="medium"
      footer={
        <>
          <Button variant="neutral" onClick={onClose}>
            Đóng
          </Button>
          <Button
            onClick={() => {
              notify("Đã áp dụng tùy chọn trên trình duyệt. Âm thanh chỉ bật khi bạn chủ động yêu cầu.")
              onClose()
            }}
          >
            Lưu tùy chọn
          </Button>
        </>
      }
    >
      <div className="form-stack">
        <div className="switch-setting">
          <Volume2 size={22} className="muted" />
          <SettingSwitch
            resetKey={audioError}
            label="Âm thanh nước đi"
            description="Âm gỗ riêng cho 7 quân; luôn tắt khi mở lại ứng dụng."
            selected={soundEnabled}
            disabled={audioPending}
            onChange={() => void toggleSound()}
          />
        </div>
        {audioError && <div className="error-message" role="alert"><AlertCircle size={16} />{audioError}</div>}
        <InputField label={`Âm lượng · ${Math.round(settings.volume * 100)}%`} aria-label="Âm lượng" type="range" min="0" max="100" step="1" value={String(Math.round(settings.volume * 100))} onChange={(value) => updateSettings({ volume: Number(value) / 100 })} />
        <SettingSwitch label="Âm thanh êm dịu" description="Giảm cường độ và tiếng bật mạnh. Tự áp dụng khi ứng dụng đang giảm chuyển động." selected={settings.quietAudio} onChange={(value) => updateSettings({ quietAudio: value })} />
        <div className="sound-sample-row">
          <SelectField label="Nghe thử âm thanh" value={sample} onChange={(value) => setSample(value as AudioCue)} options={[
            ...(["Tướng", "Sĩ", "Tượng", "Mã", "Xe", "Pháo", "Tốt"] as const).map((value) => ({ value, label: value })),
            { value: "capture", label: "Ăn quân" }, { value: "check", label: "Chiếu tướng" }, { value: "mate", label: "Chiếu bí / chiến thắng" },
          ]} />
          <Button variant="neutral" disabled={!soundEnabled || audioPending} onClick={() => playCue(sample)}>Nghe thử</Button>
        </div>
        <SettingSwitch label="Linh khí sàn đấu" description="Ánh sáng, sương nhẹ và hiệu ứng kết liễu sau chiếu bí." selected={settings.effects} onChange={(value) => updateSettings({ effects: value })} />
        <SettingSwitch label="Âm dương trên bàn cờ" description="Lớp phủ mờ, nằm dưới đường kẻ và quân cờ." selected={settings.yinYang} onChange={(value) => updateSettings({ yinYang: value })} />
        <SelectField
          label="Chuyển động"
          className="motion-preference-field"
          value={settings.motionPreference}
          options={[
            { value: "system", label: "Theo thiết bị" },
            { value: "reduce", label: "Giảm chuyển động" },
            { value: "allow", label: "Cho phép chuyển động" },
          ]}
          onChange={(value) => updateSettings({ motionPreference: value as MotionPreference })}
          description={
            settings.motionPreference === "system"
              ? `Thiết bị hiện ${systemReducedMotion ? "giảm" : "cho phép"} chuyển động. Tự cập nhật khi thiết lập hệ điều hành thay đổi.`
              : settings.motionPreference === "reduce"
                ? "Dừng hoạt cảnh trang trí; giữ rõ lượt đi, cảnh báo chiếu và nước vừa đi."
                : "Cho phép hoạt cảnh trang trí, không phụ thuộc thiết lập của thiết bị."
          }
        />
        <div className="switch-setting">
          <Eye size={22} className="muted" />
          <SettingSwitch
            label="Làm nổi bật nước vừa đi"
            description="Dễ dàng theo dõi thế cờ đang thay đổi."
            selected={settings.highlightMoves}
            onChange={(value) => updateSettings({ highlightMoves: value })}
          />
        </div>
        <div className="info-message">
          <ShieldCheck size={16} />
          <span>
            Tùy chọn hiển thị và âm lượng được lưu cục bộ. Âm thanh tự tổng hợp bằng Web Audio, không dùng bản ghi có bản quyền; không tự phát khi vừa mở trang.
          </span>
        </div>
        {storageError && <div className="error-message" role="alert">{storageError}</div>}
      </div>
    </Modal>
  )
}

function RankGuide({ onClose }: { onClose: () => void }) {
  const { demoElo } = useExperience()
  const current = getCultivationRank(demoElo)
  return <Modal isOpen onClose={onClose} title="Lộ trình 13 cảnh giới" size="large">
    <div className="info-message"><ShieldCheck size={17} /><span>Ngưỡng Elo minh họa riêng của Kỳ Tiên Hội, có thể điều chỉnh trong cấu hình; không phải tiêu chuẩn xếp hạng quốc tế. Mỗi cảnh giới có {CULTIVATION_LAYERS} tầng.</span></div>
    <div className="realm-guide-grid">{CULTIVATION_RANKS.map((realm, index) => <div className={`realm-guide-item cultivation-${index} ${current.index === index ? "current-realm" : ""}`} key={realm.name}>
      <UserAvatar initials={String(index + 1).padStart(2, "0")} elo={realm.minElo} size="medium" />
      <div><RankBadge elo={realm.minElo} /><div className="small muted">Từ {realm.minElo.toLocaleString("vi-VN")} Elo{current.index === index ? " · Bạn đang ở đây" : ""}</div></div>
    </div>)}</div>
    <div className="form-actions"><Button onClick={onClose}>Đã hiểu</Button></div>
  </Modal>
}
