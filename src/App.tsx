import { useEffect, useState, type ReactNode } from "react"
import {
  Button,
  IconButton,
  SidebarButton,
  SidebarNavigation,
  ThemeProvider,
  useTheme,
} from "@figma/astraui"
import {
  AlertCircle,
  ArrowRight,
  Bell,
  BookOpen,
  Bot,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  History as HistoryIcon,
  Home as HomeIcon,
  Info,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  Swords,
  Trophy,
  User,
  X,
} from "lucide-react"
import { Heading, OnlineStatus, UserAvatar } from "./components"
import { AppContext, type GameConfig, type ModalName } from "./context"
import {
  gameHistory,
  playerInitials,
  rooms,
  type GameRecord,
  type Page,
  type Room,
  type Side,
} from "./data"
import Home from "./pages/Home"
import Rooms from "./pages/Rooms"
import Auth from "./pages/Auth"
import { AISetup, Game, Replay, WaitingRoom } from "./pages/Play"
import { History, Leaderboard, Profile } from "./pages/Community"
import { GlobalDialogs } from "./dialogs"
import { ExperienceProvider, useExperience } from "./experience/Experience"

const slugs: Record<Page, string> = {
  home: "sanh-chinh",
  rooms: "sanh-dau",
  ai: "choi-voi-may",
  waiting: "phong-cho",
  game: "van-co",
  history: "lich-su",
  replay: "xem-lai",
  leaderboard: "bang-xep-hang",
  profile: "ho-so",
  login: "dang-nhap",
  register: "dang-ky",
  forgot: "quen-mat-khau",
  otp: "xac-minh-email",
  reset: "mat-khau-moi",
}
const pageNames: Record<Page, string> = {
  home: "Sảnh chính",
  rooms: "Sảnh đấu",
  ai: "Chơi với máy",
  waiting: "Phòng chờ",
  game: "Ván cờ",
  history: "Lịch sử ván đấu",
  replay: "Xem lại ván cờ",
  leaderboard: "Bảng Phong Thần",
  profile: "Hồ sơ kỳ thủ",
  login: "Đăng nhập",
  register: "Đăng ký",
  forgot: "Quên mật khẩu",
  otp: "Xác minh email",
  reset: "Mật khẩu mới",
}
function pageFromHash(): Page {
  const hash = window.location.hash.replace("#", "").split("?")[0]
  return (
    (Object.keys(slugs) as Page[]).find((page) => slugs[page] === hash) ||
    "home"
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ExperienceProvider><Application /></ExperienceProvider>
    </ThemeProvider>
  )
}

function Application() {
  const { setTheme } = useTheme()
  const { reducedMotion, settings, profile, setDemoName: setUsername } = useExperience()
  const username = profile.name
  const profileTone = profile.tone
  const [page, setPage] = useState<Page>(pageFromHash)
  const [modal, setModal] = useState<ModalName>(null)
  const [signedIn, setSignedIn] = useState(true)
  const [roomList, setRoomList] = useState(rooms)
  const [activeRoom, setActiveRoom] = useState(rooms[0])
  const [isHost, setIsHost] = useState(false)
  const [gameConfig, setGameConfig] = useState<GameConfig>({
    mode: "ai",
    side: "red",
    difficulty: "medium",
    key: 0,
  })
  const [authFlow, setAuthFlow] = useState<"register" | "reset" | "activate">(
    "register",
  )
  const [authEmail, setAuthEmail] = useState("")
  const [selectedRecord, setSelectedRecord] = useState(gameHistory[0])
  const [notification, setNotification] = useState<{
    message: string
    type: "success" | "error" | "info"
    key: number
  } | null>(null)
  const [mobileNav, setMobileNav] = useState(false)
  const [profileMenu, setProfileMenu] = useState(false)
  const [bellMenu, setBellMenu] = useState(false)
  useEffect(() => {
    setTheme("light")
  }, [])
  useEffect(() => {
    const onHash = () => {
      setPage(pageFromHash())
      setModal(null)
      setMobileNav(false)
      document.querySelector(".main-scroll")?.scrollTo({ top: 0 })
    }
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])
  useEffect(() => {
    if (!notification) return
    const timer = setTimeout(() => setNotification(null), 4300)
    return () => clearTimeout(timer)
  }, [notification])
  useEffect(() => {
    document.title = `${pageNames[page]} · Kỳ Tiên Hội`
    setProfileMenu(false)
    setBellMenu(false)
  }, [page])
  function go(next: Page) {
    setPage(next)
    setMobileNav(false)
    setModal(null)
    setProfileMenu(false)
    setBellMenu(false)
    window.location.hash = slugs[next]
    document
      .querySelector(".main-scroll")
      ?.scrollTo({ top: 0, behavior: "instant" })
  }
  function notify(
    message: string,
    type: "success" | "error" | "info" = "success",
  ) {
    setNotification({ message, type, key: Date.now() })
  }
  function joinRoom(room: Room) {
    if (room.playing && !room.spectators) {
      notify("Phòng đã đủ người và không cho phép khán giả.", "error")
      return
    }
    setActiveRoom(room)
    setIsHost(Boolean(room.ownedByMe))
    if (room.private) setModal("password")
    else go("waiting")
  }
  function startGame(
    mode: "ai" | "online",
    side: Side = "red",
    difficulty = "medium",
    spectator = false,
  ) {
    setGameConfig((config) => ({
      mode,
      side,
      difficulty,
      key: config.key + 1,
      spectator,
    }))
    go("game")
  }
  function viewRecord(record: GameRecord) {
    setSelectedRecord(record)
    go("replay")
  }
  function roomForProfile(room: Room): Room {
    return room.ownedByMe
      ? { ...room, host: username, initials: playerInitials(username), tone: profileTone }
      : room
  }
  const context = {
    page,
    go,
    openModal: (next: ModalName) => {
      // A toast from the previous save must not cover the editor's action bar.
      if (next === "edit") setNotification(null)
      setModal(next)
    },
    closeModal: () => setModal(null),
    notify,
    signedIn,
    setSignedIn,
    username,
    setUsername,
    profileTone,
    roomList: roomList.map(roomForProfile),
    setRoomList,
    activeRoom: roomForProfile(activeRoom),
    setActiveRoom,
    isHost,
    setIsHost,
    joinRoom,
    gameConfig,
    startGame,
    authFlow,
    setAuthFlow,
    authEmail,
    setAuthEmail,
    selectedRecord,
    viewRecord,
  }
  const navItems = [
    { page: "home" as Page, label: "Sảnh chính", icon: HomeIcon },
    { page: "ai" as Page, label: "Chơi với máy", icon: Bot },
    { page: "rooms" as Page, label: "Sảnh đấu", icon: Swords, count: "24" },
    { page: "leaderboard" as Page, label: "Bảng Phong Thần", icon: Trophy },
    { page: "history" as Page, label: "Lịch sử ván đấu", icon: HistoryIcon },
    { page: "profile" as Page, label: "Hồ sơ của tôi", icon: User },
  ]
  const activeNav =
    page === "waiting" || (page === "game" && gameConfig.mode === "online")
      ? "rooms"
      : page === "game"
        ? "ai"
        : page === "replay"
          ? "history"
          : page
  function renderPage(): ReactNode {
    switch (page) {
      case "home":
        return <Home />
      case "rooms":
        return <Rooms />
      case "ai":
        return <AISetup />
      case "waiting":
        return <WaitingRoom key={activeRoom.id} />
      case "game":
        return <Game key={gameConfig.key} />
      case "history":
        return <History />
      case "replay":
        return <Replay key={selectedRecord.id} />
      case "leaderboard":
        return <Leaderboard />
      case "profile":
        return <Profile />
      default:
        return <Auth />
    }
  }
  return (
    <AppContext.Provider value={context}>
      <div
        className={`app app-page-${page} ${reducedMotion ? "experience-reduced" : ""}`}
        data-motion-preference={settings.motionPreference}
      >
        {mobileNav && (
          <div
            className="mobile-nav-scrim"
            onClick={() => setMobileNav(false)}
          />
        )}
        <aside className={`sidebar-shell ${mobileNav ? "sidebar-open" : ""}`}>
          <Button
            variant="subtle"
            className="brand"
            onClick={() => go("home")}
            aria-label="Kỳ Tiên Hội — về sảnh chính"
          >
            <span className="brand-mark">
              <span>K</span>
            </span>
            <span className="brand-copy">
              <span className="brand-name">
                Kỳ Tiên Hội<span className="brand-name-dot">.</span>
              </span>
              <span className="brand-tagline">CỜ TƯỚNG · BẢN DEMO</span>
            </span>
          </Button>
          <SidebarNavigation
            className="app-sidebar"
            footer={
              <>
                <div className="beginner-card">
                  <span className="beginner-icon">
                    <BookOpen size={20} strokeWidth={1.5} />
                  </span>
                  <Heading level={3}>Vạn dặm, từ một nước đi.</Heading>
                  <div className="small muted">
                    Làm quen luật cờ và tự tin
                    <br />
                    bắt đầu ván đầu tiên.
                  </div>
                  <Button
                    variant="subtle"
                    size="small"
                    iconEnd={<ArrowRight size={15} />}
                    onClick={() => setModal("rules")}
                  >
                    Luật cờ tướng
                  </Button>
                </div>
                <SidebarButton
                  icon={
                    <span className="nav-item-content">
                      <Settings size={19} strokeWidth={1.6} />
                      <span>Cài đặt</span>
                    </span>
                  }
                  className="sidebar-nav-button settings-nav"
                  onClick={() => setModal("settings")}
                  title="Cài đặt"
                />
              </>
            }
          >
            <div className="nav-section-label">KHÔNG GIAN CỦA BẠN</div>
            {navItems.map(({ page: target, label, icon: Icon, count }, i) => (
              <div key={target} className="nav-item-wrap">
                {i === 3 && (
                  <div className="nav-section-label secondary-label">
                    CỘNG ĐỒNG KỲ THỦ
                  </div>
                )}
                <SidebarButton
                  icon={
                    <span className="nav-item-content">
                      <Icon size={19} strokeWidth={1.7} />
                      <span>{label}</span>
                      {count && <span className="nav-count">{count}</span>}
                    </span>
                  }
                  active={activeNav === target}
                  className={`sidebar-nav-button ${
                    activeNav === target ? "nav-active" : ""
                  }`}
                  onClick={() => go(target)}
                  title={label}
                />
              </div>
            ))}
          </SidebarNavigation>
          <div className="sidebar-bottom-caption">
            Tâm tĩnh. Trí sáng. Cờ hay.
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="topbar-start">
              <IconButton
                icon={<Menu size={21} />}
                variant="subtle"
                className="mobile-menu-button"
                aria-label="Mở điều hướng"
                onClick={() => setMobileNav((v) => !v)}
              />
              <div className="breadcrumbs">
                <HomeIcon size={16} />
                <ChevronRight size={13} />
                <span>{pageNames[page]}</span>
                {page === "home" && (
                  <>
                    <span className="breadcrumb-divider" />
                    <span className="breadcrumb-welcome">
                      Chào mừng trở lại!
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="topbar-end">
              <OnlineStatus muted>
                <strong>1.248</strong> kỳ hữu · demo
              </OnlineStatus>
              <span className="topbar-divider" />
              <div className="popover-anchor">
                <IconButton
                  variant="subtle"
                  icon={<Bell size={19} strokeWidth={1.7} />}
                  aria-label="Thông báo"
                  className="notification-button"
                  onClick={() => {
                    setBellMenu((v) => !v)
                    setProfileMenu(false)
                  }}
                />
                <span className="bell-dot" />
                {bellMenu && (
                  <div className="header-popover notification-popover">
                    <Heading level={3}>Thông báo</Heading>
                    <div className="notification-item">
                      <span className="quick-icon tone-sage">
                        <ShieldCheck size={19} />
                      </span>
                      <div>
                        <div className="player-name">
                          Chào mừng đến với Kỳ Tiên Hội
                        </div>
                        <div className="muted small">
                          Một cộng đồng văn minh, một niềm đam mê.
                        </div>
                      </div>
                    </div>
                    <div className="notification-item">
                      <span className="quick-icon tone-sand">
                        <Swords size={19} />
                      </span>
                      <div>
                        <div className="player-name">Sẵn sàng khai cuộc?</div>
                        <div className="muted small">
                          Có 24 bàn cờ mẫu để trải nghiệm.
                        </div>
                        <Button
                          variant="subtle"
                          size="small"
                          className="text-link"
                          onClick={() => go("rooms")}
                        >
                          Khám phá sảnh đấu
                          <ArrowRight size={13} />
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              {signedIn ? (
                <div className="popover-anchor">
                  <Button
                    variant="subtle"
                    className="topbar-user"
                    aria-label={`Tài khoản của ${username}`}
                    aria-expanded={profileMenu}
                    aria-controls={profileMenu ? "account-menu" : undefined}
                    title="Menu tài khoản"
                    onClick={() => {
                      setProfileMenu((v) => !v)
                      setBellMenu(false)
                    }}
                  >
                    <UserAvatar
                      initials={playerInitials(username)}
                      tone={profileTone}
                      size="medium"
                      current
                    />
                    <ChevronDown size={14} className="muted" />
                  </Button>
                  {profileMenu && (
                    <div id="account-menu" className="header-popover profile-popover">
                      <Button
                        variant="subtle"
                        iconStart={<User size={16} />}
                        onClick={() => go("profile")}
                      >
                        Hồ sơ của tôi
                      </Button>
                      <Button
                        variant="subtle"
                        iconStart={<HistoryIcon size={16} />}
                        onClick={() => go("history")}
                      >
                        Lịch sử ván đấu
                      </Button>
                      <Button
                        variant="subtle"
                        iconStart={<Settings size={16} />}
                        onClick={() => {
                          setProfileMenu(false)
                          setModal("settings")
                        }}
                      >
                        Cài đặt
                      </Button>
                      <Button
                        variant="subtle"
                        iconStart={<LogOut size={16} />}
                        onClick={() => {
                          setSignedIn(false)
                          setProfileMenu(false)
                          go("home")
                          notify("Bạn đang trải nghiệm ở chế độ khách.", "info")
                        }}
                      >
                        Đăng xuất
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="inline">
                  <Button
                    variant="subtle"
                    size="small"
                    onClick={() => go("login")}
                  >
                    Đăng nhập
                  </Button>
                  <Button size="small" onClick={() => go("register")}>
                    Đăng ký
                  </Button>
                </div>
              )}
            </div>
          </header>
          <main className="main-scroll">
            <div className="page-container">{renderPage()}</div>
          </main>
        </div>
        <nav
          className="mobile-bottom-nav"
          aria-label="Điều hướng trên điện thoại"
        >
          {[
            { page: "home" as Page, icon: HomeIcon, label: "Sảnh chính" },
            { page: "rooms" as Page, icon: Swords, label: "Sảnh đấu" },
            { page: "ai" as Page, icon: Bot, label: "Với máy" },
            { page: "profile" as Page, icon: User, label: "Hồ sơ" },
          ].map(({ page: target, icon: Icon, label }) => (
            <Button
              variant="subtle"
              key={target}
              className={activeNav === target ? "active" : ""}
              onClick={() => go(target)}
            >
              <Icon size={20} strokeWidth={1.7} />
              <span>{label}</span>
            </Button>
          ))}
        </nav>
        <GlobalDialogs modal={modal} onClose={() => setModal(null)} />
        {notification && (
          <div
            className="notification-host"
            role={notification.type === "error" ? "alert" : "status"}
            key={notification.key}
          >
            <div className={`notification notification-${notification.type}`}>
              {notification.type === "error" ? (
                <AlertCircle size={19} />
              ) : notification.type === "success" ? (
                <CheckCircle size={19} />
              ) : (
                <Info size={19} />
              )}
              <span>{notification.message}</span>
              <IconButton
                variant="subtle"
                icon={<X size={16} />}
                aria-label="Đóng thông báo"
                size="small"
                onClick={() => setNotification(null)}
              />
            </div>
          </div>
        )}
      </div>
    </AppContext.Provider>
  )
}
