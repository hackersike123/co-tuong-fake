import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { Heading, UserAvatar } from "./components";
import {
  AppContext,
  type GameConfig,
  type ModalName,
  type PlayerAccount,
  type RoomAccess,
} from "./context";
import {
  playerInitials,
  type CommunitySummary,
  type GameRecord,
  type Page,
  type PlayerStats,
  type RankedPlayer,
  type Room,
  type Side,
} from "./data";
import { WebSocketRpcClient } from "./services/socket";
import { ApiError, apiFetch } from "./services/api";
import { INITIAL_ELO } from "./ranks";
import Home from "./pages/Home";
import Rooms from "./pages/Rooms";
import Auth from "./pages/Auth";
import { AISetup, Game, Replay, WaitingRoom } from "./pages/Play";
import { History, Leaderboard, Profile } from "./pages/Community";
import { GlobalDialogs } from "./dialogs";
import { ExperienceProvider, useExperience } from "./experience/Experience";
import { useLanguage } from "./i18n";
import { intlLocale, translateText } from "./i18n-core";
import {
  requiresRoomExitConfirmation,
  shouldApplyAuthRefresh,
  trackPendingRequest,
  waitForPendingRequests,
} from "./room-interactions";
import { buildRoomCodeJoinPayload } from "./room-join";

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
    roomCode: access.room_code || String(access.id),
    name: access.room_name,
    host: access.host_name,
    initials: playerInitials(access.host_name),
    elo: access.host_elo,
    seconds: access.timer_seconds,
    players: access.player_count,
    private: !access.is_public,
    playing: access.status === "playing",
    spectators: access.allow_spectators,
    tone: "sage",
    player2Name: access.player2_name,
    player2Elo: access.player2_elo,
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
  const { language, toggleLanguage } = useLanguage();
  const locale = intlLocale(language);
  const { reducedMotion, settings, profile, setProfileName: setUsername, setElo } = useExperience();
  const username = profile.name;
  const profileTone = profile.tone;
  const socketRpc = useMemo(() => new WebSocketRpcClient(), []);
  const [authToken, setAuthTokenState] = useState(
    () => sessionStorage.getItem("co-tuong-access-token") || "",
  );
  const authEpochRef = useRef(0);
  const logoutInProgressRef = useRef(false);
  const pendingRefreshRequestsRef = useRef(new Set<Promise<unknown>>());
  const [page, setPage] = useState<Page>(pageFromHash);
  const pageRef = useRef(page);
  const [modal, setModal] = useState<ModalName>(null);
  const [signedIn, setSignedInState] = useState(Boolean(authToken));
  const [currentUser, setCurrentUser] = useState<PlayerAccount | null>(null);
  const [playerStats, setPlayerStats] = useState<PlayerStats | null>(null);
  const [leaderboard, setLeaderboard] = useState<RankedPlayer[]>([]);
  const [recentMatches, setRecentMatches] = useState<GameRecord[]>([]);
  const [myMatches, setMyMatches] = useState<GameRecord[]>([]);
  const [communitySummary, setCommunitySummary] = useState<CommunitySummary | null>(null);
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
  const [selectedRecord, setSelectedRecord] = useState<GameRecord | null>(null);
  const [notification, setNotification] = useState<{
    message: string;
    type: "success" | "error" | "info";
    key: number;
  } | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [profileMenu, setProfileMenu] = useState(false);
  const [bellMenu, setBellMenu] = useState(false);
  function rpcRequest<T>(event: string, data: Record<string, unknown> = {}, timeoutMs?: number) {
    const payload =
      authToken && !event.startsWith("auth.") ? { ...data, auth_token: authToken } : data;
    return socketRpc.request<T>(event, payload, timeoutMs);
  }
  const requestRefreshToken = useCallback(
    () =>
      trackPendingRequest(
        pendingRefreshRequestsRef.current,
        apiFetch<{ access_token: string }>("/api/v1/auth/refresh", { method: "POST" }),
      ),
    [],
  );
  const refreshData = useCallback(async () => {
    const requestEpoch = authEpochRef.current;
    const [summaryResult, leaderboardResult, recentResult] = await Promise.allSettled([
      apiFetch<CommunitySummary>("/api/v1/community/summary"),
      apiFetch<RankedPlayer[]>("/api/v1/community/leaderboard"),
      apiFetch<GameRecord[]>("/api/v1/community/recent-matches"),
    ]);
    if (summaryResult.status === "fulfilled") setCommunitySummary(summaryResult.value);
    if (leaderboardResult.status === "fulfilled") setLeaderboard(leaderboardResult.value);
    if (recentResult.status === "fulfilled") setRecentMatches(recentResult.value);

    if (!authToken) {
      if (logoutInProgressRef.current) {
        setCurrentUser(null);
        setPlayerStats(null);
        setMyMatches([]);
        setSignedInState(false);
        setElo(INITIAL_ELO);
        return;
      }
      try {
        const refreshed = await requestRefreshToken();
        if (
          refreshed.access_token &&
          shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
        ) {
          setAuthToken(refreshed.access_token);
          return;
        }
      } catch {
        // A guest has no refresh cookie; continue with public data.
      }
      if (
        !shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
      ) {
        return;
      }
      setCurrentUser(null);
      setPlayerStats(null);
      setMyMatches([]);
      setSignedInState(false);
      setElo(INITIAL_ELO);
      return;
    }
    try {
      const [user, stats, matches] = await Promise.all([
        apiFetch<PlayerAccount>("/api/v1/users/me", { token: authToken }),
        apiFetch<PlayerStats>("/api/v1/users/me/stats", { token: authToken }),
        apiFetch<GameRecord[]>("/api/v1/users/me/matches", {
          token: authToken,
        }),
      ]);
      if (
        !shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
      ) {
        return;
      }
      setCurrentUser(user);
      setPlayerStats(stats);
      setMyMatches(matches);
      setUsername(user.display_name);
      setElo(user.elo);
      setSignedInState(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (
          !shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
        ) {
          return;
        }
        try {
          const refreshed = await requestRefreshToken();
          if (
            refreshed.access_token &&
            shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
          ) {
            setAuthToken(refreshed.access_token);
            return;
          }
        } catch {
          if (
            shouldApplyAuthRefresh(requestEpoch, authEpochRef.current, logoutInProgressRef.current)
          ) {
            setAuthToken("");
          }
        }
      }
    }
  }, [authToken, requestRefreshToken, setElo, setUsername]);
  useEffect(() => {
    void refreshData();
  }, [refreshData]);
  useEffect(() => {
    setTheme("light");
  }, []);
  useEffect(() => () => socketRpc.close(), [socketRpc]);
  useEffect(() => {
    let cancelled = false;
    void rpcRequest<
      Array<{
        id: number;
        room_code: string;
        room_name: string;
        host_name: string;
        host_elo?: number | null;
        player2_name?: string | null;
        player2_elo?: number | null;
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
            roomCode: room.room_code,
            name: room.room_name,
            host: room.host_name,
            initials: playerInitials(room.host_name),
            elo: room.host_elo,
            seconds: room.timer_seconds as 15 | 30 | 60,
            players: room.player_count,
            private: !room.is_public,
            playing: room.status === "playing",
            spectators: room.allow_spectators,
            tone: "sage",
            player2Name: room.player2_name,
            player2Elo: room.player2_elo,
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
      const nextPage = pageFromHash();
      if (nextPage === pageRef.current) return;
      go(nextPage);
      setModal(null);
      setMobileNav(false);
      document.querySelector(".main-scroll")?.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [page, roomAccess, gameConfig.mode, language]);
  useEffect(() => {
    const match = /^\/room\/([0-9]+)\/?$/.exec(window.location.pathname);
    if (!match) return;
    let cancelled = false;
    const inviteToken = new URLSearchParams(window.location.search).get("token");
    void rpcRequest<RoomAccess>("room.join", {
      room_id: Number(match[1]),
      invite_token: inviteToken || undefined,
      participant_name: username,
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
    document.title = `${translateText(pageNames[page], language)} · ${
      language === "en" ? "Ky Tien Hoi" : "Kỳ Tiên Hội"
    }`;
    setProfileMenu(false);
    setBellMenu(false);
  }, [page, language]);
  function canLeaveActiveRoom(next: Page): boolean {
    if (
      !requiresRoomExitConfirmation(
        page,
        next,
        Boolean(roomAccess && roomAccess.role !== "spectator"),
        gameConfig.mode,
      )
    ) {
      return true;
    }
    const warning =
      page === "waiting"
        ? roomAccess?.role === "player1"
          ? "Rời phòng chờ sẽ đóng phòng cho những người đang tham gia. Bạn có muốn tiếp tục?"
          : "Rời phòng chờ sẽ ngắt kết nối và bạn có thể phải vào lại. Bạn có muốn tiếp tục?"
        : "Rời ván online sẽ ngắt kết nối; nếu ván chưa kết thúc và bạn không quay lại trong thời gian cho phép, bạn có thể bị xử thua. Bạn có muốn tiếp tục?";
    return window.confirm(translateText(warning, language));
  }
  function go(next: Page, bypassRoomConfirmation = false) {
    if (!bypassRoomConfirmation && !canLeaveActiveRoom(next)) {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}#${slugs[pageRef.current]}`,
      );
      return;
    }
    pageRef.current = next;
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
    authEpochRef.current += 1;
    if (token) logoutInProgressRef.current = false;
    setAuthTokenState(token);
    setSignedInState(Boolean(token));
    if (token) sessionStorage.setItem("co-tuong-access-token", token);
    else {
      sessionStorage.removeItem("co-tuong-access-token");
      setCurrentUser(null);
      setPlayerStats(null);
      setMyMatches([]);
      setElo(INITIAL_ELO);
    }
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
      const access = await rpcRequest<RoomAccess>("room.join", {
        room_id: roomId,
        participant_name: username,
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
    const access = await rpcRequest<RoomAccess>("room.join", {
      room_id: roomId,
      password,
      participant_name: username,
    });
    acceptRoomAccess(access);
  }
  async function joinRoomByCode(code: string, password?: string) {
    try {
      const access = await rpcRequest<RoomAccess>("room.join_code", {
        ...buildRoomCodeJoinPayload(code, username, password),
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
    go("game", mode === "online");
  }
  function viewRecord(record: GameRecord) {
    setSelectedRecord(record);
    go("replay");
  }
  function roomForProfile(room: Room): Room {
    return room.ownedByMe
      ? {
          ...room,
          host: username,
          initials: playerInitials(username),
          tone: profileTone,
        }
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
    request: rpcRequest,
    signedIn,
    setSignedIn,
    currentUser,
    setCurrentUser,
    playerStats,
    leaderboard,
    recentMatches,
    myMatches,
    communitySummary,
    refreshData,
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
    { page: "rooms" as Page, label: "Sảnh đấu", icon: Swords },
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
        return <Replay key={selectedRecord?.id ?? "missing-record"} />;
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
              <span className="brand-tagline">CỜ TƯỚNG TRỰC TUYẾN</span>
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
            {navItems.map(({ page: target, label, icon: Icon }, i) => (
              <div key={target} className="nav-item-wrap">
                {i === 3 && (
                  <div className="nav-section-label secondary-label">CỘNG ĐỒNG KỲ THỦ</div>
                )}
                <SidebarButton
                  icon={
                    <span className="nav-item-content">
                      <Icon size={19} strokeWidth={1.7} />
                      <span>{label}</span>
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
                    <span className="breadcrumb-welcome">
                      {signedIn ? "Chào mừng trở lại!" : "Bàn cờ luôn mở."}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="topbar-end">
              <span className="small muted">
                <strong>
                  {communitySummary?.registered_players.toLocaleString(locale) ?? "—"}
                </strong>{" "}
                tài khoản
              </span>
              <Button
                variant="subtle"
                size="small"
                className="language-switch-button"
                aria-label={language === "vi" ? "Chuyển sang tiếng Anh" : "Chuyển sang tiếng Việt"}
                title={language === "vi" ? "Chuyển sang tiếng Anh" : "Chuyển sang tiếng Việt"}
                onClick={toggleLanguage}
              >
                {language === "vi" ? "EN" : "VI"}
              </Button>
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
                {bellMenu && (
                  <div className="header-popover notification-popover">
                    <Heading level={3}>Thông báo</Heading>
                    <div className="notification-item muted small">
                      Chưa có hệ thống thông báo trên máy chủ.
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
                          if (!canLeaveActiveRoom("home")) return;
                          logoutInProgressRef.current = true;
                          authEpochRef.current += 1;
                          setSignedIn(false);
                          setProfileMenu(false);
                          go("home", true);
                          notify("Bạn đang trải nghiệm ở chế độ khách.", "info");
                          void (async () => {
                            await waitForPendingRequests(pendingRefreshRequestsRef.current);
                            try {
                              await apiFetch("/api/v1/auth/logout", { method: "POST" });
                            } catch {
                              notify(
                                "Không xác nhận được việc đăng xuất. Hãy thử lại khi có kết nối.",
                                "error",
                              );
                            }
                          })();
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
