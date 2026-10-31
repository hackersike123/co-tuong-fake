import { createContext, useContext } from "react";
import type { Dispatch, SetStateAction } from "react";
import type {
  CommunitySummary,
  GameRecord,
  Page,
  PlayerStats,
  RankedPlayer,
  Room,
  Side,
} from "./data";

export type PlayerAccount = {
  id: number;
  display_name: string;
  email: string;
  username: string | null;
  is_active: boolean;
  created_at: string;
  elo: number;
};

export type ModalName =
  | "create"
  | "password"
  | "share"
  | "rules"
  | "tips"
  | "settings"
  | "edit"
  | "ranks"
  | null;
export type GameConfig = {
  mode: "ai" | "online";
  side: Side;
  difficulty: string;
  key: number;
  spectator?: boolean;
};
export type RoomAccess = {
  id: number;
  room_id: number;
  room_uuid: string;
  room_code: string;
  room_name: string;
  name: string;
  host_name: string;
  host_elo?: number | null;
  player2_name?: string | null;
  player2_elo?: number | null;
  visibility: "public" | "private";
  is_public: boolean;
  has_password: boolean;
  allow_spectators: boolean;
  player2_ready: boolean;
  status: "waiting" | "playing" | "finished";
  player_count: number;
  spectator_count: number;
  created_at: number;
  timer_seconds: 15 | 30 | 60;
  time_per_move: 15 | 30 | 60;
  role: "player1" | "player2" | "spectator";
  participant_token: string;
  join_url: string;
};
export type AppContextValue = {
  page: Page;
  go: (page: Page) => void;
  openModal: (modal: ModalName) => void;
  closeModal: () => void;
  notify: (message: string, type?: "success" | "error" | "info") => void;
  request: <T = unknown>(
    event: string,
    data?: Record<string, unknown>,
    timeoutMs?: number,
  ) => Promise<T>;
  authToken: string;
  setAuthToken: (token: string) => void;
  signedIn: boolean;
  setSignedIn: (value: boolean) => void;
  currentUser: PlayerAccount | null;
  setCurrentUser: (value: PlayerAccount | null) => void;
  playerStats: PlayerStats | null;
  leaderboard: RankedPlayer[];
  recentMatches: GameRecord[];
  myMatches: GameRecord[];
  communitySummary: CommunitySummary | null;
  refreshData: () => Promise<void>;
  username: string;
  setUsername: (value: string) => void;
  profileTone: string;
  roomList: Room[];
  setRoomList: React.Dispatch<React.SetStateAction<Room[]>>;
  activeRoom: Room;
  setActiveRoom: Dispatch<SetStateAction<Room>>;
  roomAccess: RoomAccess | null;
  setRoomAccess: (access: RoomAccess | null) => void;
  isHost: boolean;
  setIsHost: (value: boolean) => void;
  joinRoom: (room: Room) => void;
  joinRoomWithPassword: (password: string) => Promise<void>;
  joinRoomByCode: (code: string) => Promise<void>;
  gameConfig: GameConfig;
  startGame: (mode: "ai" | "online", side?: Side, difficulty?: string, spectator?: boolean) => void;
  authFlow: "register" | "reset" | "activate";
  setAuthFlow: (value: "register" | "reset" | "activate") => void;
  authEmail: string;
  setAuthEmail: (value: string) => void;
  selectedRecord: GameRecord | null;
  viewRecord: (record: GameRecord) => void;
};

export const AppContext = createContext<AppContextValue | null>(null);
export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("AppContext is required");
  return context;
}
