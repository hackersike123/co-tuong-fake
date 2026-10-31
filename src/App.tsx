import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Button,
  IconButton,
  SidebarButton,
  SidebarNavigation,
  ThemeProvider,
  useTheme,
} from "@figma/astraui";
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
} from "lucide-react";
import { Heading, OnlineStatus, UserAvatar } from "./components";
import { AppContext, type GameConfig, type ModalName, type RoomAccess } from "./context";
import {
  gameHistory,
  playerInitials,
  type GameRecord,
  type Page,
  type Room,
  type Side,
} from "./data";
import { WebSocketRpcClient } from "./services/socket";
import Home from "./pages/Home";
import Rooms from "./pages/Rooms";
import Auth from "./pages/Auth";
import { AISetup, Game, Replay, WaitingRoom } from "./pages/Play";
import { History, Leaderboard, Profile } from "./pages/Community";
import { GlobalDialogs } from "./dialogs";
import { ExperienceProvider, useExperience } from "./experience/Experience";

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
};
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
};
function pageFromHash(): Page {
  const hash = window.location.hash.replace("#", "").split("?")[0];
  return (Object.keys(slugs) as Page[]).find((page) => slugs[page] === hash) || "home";
}

function loadStoredRoomAccess(): RoomAccess | null {
  try {
    const raw = sessionStorage.getItem("co-tuong-room-access");
    if (!raw) return null;
    const access = JSON.parse(raw) as RoomAccess;
    return access.participant_token && access.id > 0 ? access : null;
  } catch {
    return null;
  }
}

function roomViewFromAccess(access: RoomAccess): Room {
  return {
    id: String(access.id),
    name: access.room_name,
    host: access.host_name,
    initials: playerInitials(access.host_name),
    elo: 1200,
    seconds: access.timer_seconds,
    players: access.player_count,
    private: !access.is_public,
    playing: access.status === "playing",
    spectators: access.allow_spectators,
    tone: "sage",
  };
}

export default function App() {
  return (
    <ThemeProvider>
      <ExperienceProvider>
        <Application />
      </ExperienceProvider>
    </ThemeProvider>
  );
}

function Application() {
  const { setTheme } = useTheme();
  const { reducedMotion, settings, profile, setDemoName: setUsername } = useExperience();
  const username = profile.name;
  const profileTone = profile.tone;
  const socketRpc = useMemo(() => new WebSocketRpcClient(), []);
  const [authToken, setAuthTokenState] = useState(
    () => sessionStorage.getItem("co-tuong-access-token") || "",
  );
  const [page, setPage] = useState<Page>(pageFromHash);
  const [modal, setModal] = useState<ModalName>(null);
  const [signedIn, setSignedInState] = useState(Boolean(authToken));
  const [roomList, setRoomList] = useState<Room[]>([]);
  const [roomAccess, setRoomAccessState] = useState<RoomAccess | null>(loadStoredRoomAccess);
  const [activeRoom, setActiveRoom] = useState<Room>(() =>
    roomAccess
      ? roomViewFromAccess(roomAccess)
      : {
          id: "0",
          name: "Chưa chọn phòng",
          host: "Kỳ hữu",
          initials: "KH",
          elo: 1200,
          seconds: 30,
          players: 0,
          spectators: true,
          tone: "sage",
        },
  );
  const [isHost, setIsHost] = useState(roomAccess?.role === "player1");
  const [gameConfig, setGameConfig] = useState<GameConfig>({
    mode: pageFromHash() === "game" && roomAccess ? "online" : "ai",
    side: roomAccess?.role === "player2" ? "black" : "red",
    difficulty: "medium",
    key: 0,
    spectator: roomAccess?.role === "spectator",
  });
  const [authFlow, setAuthFlow] = useState<"register" | "reset" | "activate">("register");
  const [authEmail, setAuthEmail] = useState("");
  const [selectedRecord, setSelectedRecord] = useState(gameHistory[0]);
  const [notification, setNotification] = useState<{
    message: string;
    type: "success" | "error" | "info";
    key: number;
  } | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [profileMenu, setProfileMenu] = useState(false);
  const [bellMenu, setBellMenu] = useState(false);
  useEffect(() => {
    setTheme("light");
  }, []);
  useEffect(() => () => socketRpc.close(), [socketRpc]);
  useEffect(() => {
    let cancelled = false;
    void socketRpc
      .request<
        Array<{
          id: number;
          room_name: string;
          host_name: string;
          timer_seconds: number;
          player_count: number;
          is_public: boolean;
          allow_spectators: boolean;
          status: string;
        }>
      >("room.list")
      .then((rooms) => {
        if (cancelled) return;
        setRoomList(
          rooms.map((room) => ({
            id: String(room.id),
            name: room.room_name,
            host: room.host_name,
            initials: playerInitials(room.host_name),
            elo: 1200,
            seconds: room.timer_seconds as 15 | 30 | 60,
            players: room.player_count,
            private: !room.is_public,
            playing: room.status === "playing",
            spectators: room.allow_spectators,
            tone: "sage",
          })),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [socketRpc]);
  useEffect(() => {
    const onHash = () => {
      setPage(pageFromHash());
      setModal(null);
      setMobileNav(false);
      document.querySelector(".main-scroll")?.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    const match = /^\/room\/([0-9]+)\/?$/.exec(window.location.pathname);
    if (!match) return;
    let cancelled = false;
    const inviteToken = new URLSearchParams(window.location.search).get("token");
    void socketRpc
      .request<RoomAccess>("room.join", {
        room_id: Number(match[1]),
        invite_token: inviteToken || undefined,
      })
      .then((access) => {
        if (!cancelled) acceptRoomAccess(access);
      })
      .catch((error) => {
        if (!cancelled)
          notify(
            error instanceof Error ? error.message : "Không thể vào phòng từ liên kết mời.",
            "error",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!notification) return;
    const timer = setTimeout(() => setNotification(null), 4300);
    return () => clearTimeout(timer);
  }, [notification]);
  useEffect(() => {
    document.title = `${pageNames[page]} · Kỳ Tiên Hội`;
    setProfileMenu(false);
    setBellMenu(false);
  }, [page]);
  function go(next: Page) {
    setPage(next);
    setMobileNav(false);
    setModal(null);
    setProfileMenu(false);
    setBellMenu(false);
    window.location.hash = slugs[next];
    document.querySelector(".main-scroll")?.scrollTo({ top: 0, behavior: "instant" });
  }
  function notify(message: string, type: "success" | "error" | "info" = "success") {
    setNotification({ message, type, key: Date.now() });
  }
  function setAuthToken(token: string) {
    setAuthTokenState(token);
    setSignedInState(Boolean(token));
    if (token) sessionStorage.setItem("co-tuong-access-token", token);
    else sessionStorage.removeItem("co-tuong-access-token");
  }
  function setSignedIn(value: boolean) {
    setSignedInState(value);
    if (!value) setAuthToken("");
  }
  function setRoomAccess(access: RoomAccess | null) {
    setRoomAccessState(access);
    if (access) sessionStorage.setItem("co-tuong-room-access", JSON.stringify(access));
    else sessionStorage.removeItem("co-tuong-room-access");
  }
  function roomFromAccess(access: RoomAccess): Room {
    return roomViewFromAccess(access);
  }
  function acceptRoomAccess(access: RoomAccess) {
    setRoomAccess(access);
    const actualRoom = roomFromAccess(access);
    setActiveRoom(actualRoom);
    setIsHost(access.role === "player1");
    if (access.status === "playing") {
      setGameConfig((config) => ({
        ...config,
        mode: "online",
        side: access.role === "player2" ? "black" : "red",
        spectator: access.role === "spectator",
        key: config.key + 1,
      }));
      go("game");
    } else go("waiting");
  }
  async function enterRoom(room: Room, options: { password?: string; invite_token?: string } = {}) {
    const roomId = Number(room.id);
    if (!Number.isSafeInteger(roomId) || roomId <= 0) {
      notify("Mã phòng không hợp lệ.", "error");
      return;
    }
    try {
      const access = await socketRpc.request<RoomAccess>("room.join", {
        room_id: roomId,
        ...options,
      });
      acceptRoomAccess(access);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể vào phòng.", "error");
    }
  }
  function joinRoom(room: Room) {
    if (room.playing && !room.spectators) {
      notify("Phòng đã đủ người và không cho phép khán giả.", "error");
      return;
    }
    setActiveRoom(room);
    setIsHost(Boolean(room.ownedByMe));
    if (room.private) setModal("password");
    else void enterRoom(room);
  }
  async function joinRoomWithPassword(password: string) {
    const roomId = Number(activeRoom.id);
    if (!Number.isSafeInteger(roomId) || roomId <= 0) {
      throw new Error("Mã phòng không hợp lệ.");
    }
    const access = await socketRpc.request<RoomAccess>("room.join", {
      room_id: roomId,
      password,
    });
    acceptRoomAccess(access);
  }
  async function joinRoomByCode(code: string) {
    const roomCode = code.trim().replace(/^KD/i, "");
    try {
      const access = await socketRpc.request<RoomAccess>("room.join_code", {
        room_code: roomCode,
      });
      acceptRoomAccess(access);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể vào phòng.", "error");
    }
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
    }));
    go("game");
  }
  function viewRecord(record: GameRecord) {
    setSelectedRecord(record);
    go("replay");
  }
  function roomForProfile(room: Room): Room {
    return room.ownedByMe
      ? { ...room, host: username, initials: playerInitials(username), tone: profileTone }
      : room;
  }
  const context = {
    page,
    go,
    openModal: (next: ModalName) => {
      // A toast from the previous save must not cover the editor's action bar.
      if (next === "edit") setNotification(null);
      setModal(next);
    },
    closeModal: () => setModal(null),
    notify,
    request: <T,>(event: string, data: Record<string, unknown> = {}, timeoutMs?: number) =>
      socketRpc.request<T>(event, data, timeoutMs),
    signedIn,
    setSignedIn,
    authToken,
    setAuthToken,
    username,
    setUsername,
    profileTone,
    roomList: roomList.map(roomForProfile),
    setRoomList,
    activeRoom: roomForProfile(activeRoom),
    setActiveRoom,
    roomAccess,
    setRoomAccess,
    isHost,
    setIsHost,
    joinRoom,
    joinRoomWithPassword,
    joinRoomByCode,
    gameConfig,
    startGame,
    authFlow,
    setAuthFlow,
    authEmail,
    setAuthEmail,
    selectedRecord,
    viewRecord,
  };
  const navItems = [
    { page: "home" as Page, label: "Sảnh chính", icon: HomeIcon },
    { page: "ai" as Page, label: "Chơi với máy", icon: Bot },
    { page: "rooms" as Page, label: "Sảnh đấu", icon: Swords, count: "24" },
    { page: "leaderboard" as Page, label: "Bảng Phong Thần", icon: Trophy },
    { page: "history" as Page, label: "Lịch sử ván đấu", icon: HistoryIcon },
    { page: "profile" as Page, label: "Hồ sơ của tôi", icon: User },
  ];
  const activeNav =
    page === "waiting" || (page === "game" && gameConfig.mode === "online")
      ? "rooms"
      : page === "game"
        ? "ai"
        : page === "replay"
          ? "history"
          : page;
  function renderPage(): ReactNode {
    switch (page) {
      case "home":
        return <Home />;
      case "rooms":
        return <Rooms />;
      case "ai":
        return <AISetup />;
      case "waiting":
        return <WaitingRoom key={activeRoom.id} />;
      case "game":
        return <Game key={gameConfig.key} />;
      case "history":
        return <History />;
      case "replay":
        return <Replay key={selectedRecord.id} />;
      case "leaderboard":
        return <Leaderboard />;
      case "profile":
        return <Profile />;
      default:
        return <Auth />;
    }
  }
  return (
    <AppContext.Provider value={context}>
      <div
        className={`app app-page-${page} ${reducedMotion ? "experience-reduced" : ""}`}
        data-motion-preference={settings.motionPreference}
      >
        {mobileNav && <div className="mobile-nav-scrim" onClick={() => setMobileNav(false)} />}
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
                  <div className="nav-section-label secondary-label">CỘNG ĐỒNG KỲ THỦ</div>
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
                  className={`sidebar-nav-button ${activeNav === target ? "nav-active" : ""}`}
                  onClick={() => go(target)}
                  title={label}
                />
              </div>
            ))}
          </SidebarNavigation>
          <div className="sidebar-bottom-caption">Tâm tĩnh. Trí sáng. Cờ hay.</div>
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
                    <span className="breadcrumb-welcome">Chào mừng trở lại!</span>
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
                    setBellMenu((v) => !v);
                    setProfileMenu(false);
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
                        <div className="player-name">Chào mừng đến với Kỳ Tiên Hội</div>
                        <div className="muted small">Một cộng đồng văn minh, một niềm đam mê.</div>
                      </div>
                    </div>
                    <div className="notification-item">
                      <span className="quick-icon tone-sand">
                        <Swords size={19} />
                      </span>
                      <div>
                        <div className="player-name">Sẵn sàng khai cuộc?</div>
                        <div className="muted small">Có 24 bàn cờ mẫu để trải nghiệm.</div>
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
                      setProfileMenu((v) => !v);
                      setBellMenu(false);
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
                          setProfileMenu(false);
                          setModal("settings");
                        }}
                      >
                        Cài đặt
                      </Button>
                      <Button
                        variant="subtle"
                        iconStart={<LogOut size={16} />}
                        onClick={() => {
                          setSignedIn(false);
                          setProfileMenu(false);
                          go("home");
                          notify("Bạn đang trải nghiệm ở chế độ khách.", "info");
                        }}
                      >
                        Đăng xuất
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="inline">
                  <Button variant="subtle" size="small" onClick={() => go("login")}>
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
        <nav className="mobile-bottom-nav" aria-label="Điều hướng trên điện thoại">
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
  );
}
