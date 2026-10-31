import { pieceSymbol, type PieceType } from "./chess/pieces";
import { INITIAL_DEMO_ELO } from "./ranks";

export type Page =
  | "home"
  | "rooms"
  | "ai"
  | "waiting"
  | "game"
  | "history"
  | "replay"
  | "leaderboard"
  | "profile"
  | "login"
  | "register"
  | "forgot"
  | "otp"
  | "reset";

export type Side = "red" | "black";

export function playerInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "KH";
  return (
    words.length > 1 ? `${words[0][0]}${words[words.length - 1][0]}` : words[0].slice(0, 2)
  ).toUpperCase();
}

export function formatClock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}
export type Room = {
  id: string;
  name: string;
  host: string;
  ownedByMe?: boolean;
  initials: string;
  elo: number;
  seconds: number;
  players: number;
  private?: boolean;
  playing?: boolean;
  spectators: boolean;
  tone: string;
};

export const rooms: Room[] = [
  {
    id: "KD2846",
    name: "Giao lưu chiều cuối tuần",
    host: "ThanhPhong",
    initials: "TP",
    elo: 1320,
    seconds: 30,
    players: 1,
    spectators: true,
    tone: "sage",
  },
  {
    id: "KD1928",
    name: "Một ván cờ, một người bạn",
    host: "CoThuSaiGon",
    initials: "CT",
    elo: 1450,
    seconds: 60,
    players: 1,
    spectators: true,
    tone: "sand",
  },
  {
    id: "KD3651",
    name: "Cờ nhanh – vui là chính",
    host: "TieuTot",
    initials: "TT",
    elo: 1180,
    seconds: 15,
    players: 1,
    spectators: true,
    tone: "blue",
  },
  {
    id: "KD4712",
    name: "Kỳ hữu Hà Nội",
    host: "BachMa",
    initials: "BM",
    elo: 1680,
    seconds: 30,
    players: 1,
    private: true,
    spectators: true,
    tone: "rose",
  },
  {
    id: "KD5830",
    name: "Đại chiến cuối tuần",
    host: "NgoaLong",
    initials: "NL",
    elo: 2140,
    seconds: 60,
    players: 2,
    playing: true,
    spectators: true,
    tone: "sage",
  },
  {
    id: "KD6204",
    name: "Tân thủ cùng tiến bộ",
    host: "MinhKhai",
    initials: "MK",
    elo: 1020,
    seconds: 60,
    players: 1,
    spectators: true,
    tone: "sand",
  },
  {
    id: "KD7318",
    name: "Bàn cờ dưới hiên",
    host: "KySiMuaThu",
    initials: "KS",
    elo: 1520,
    seconds: 30,
    players: 2,
    playing: true,
    spectators: true,
    tone: "blue",
  },
  {
    id: "KD8465",
    name: "Hội cờ những người bạn",
    host: "LamSon",
    initials: "LS",
    elo: 1375,
    seconds: 15,
    players: 1,
    private: true,
    spectators: false,
    tone: "rose",
  },
];

export type RankedPlayer = {
  name: string;
  username: string;
  initials: string;
  elo: number;
  games: number;
  rate: number;
  tone: string;
  change: number;
  avatarUrl?: string;
};

export const rankings: RankedPlayer[] = [
  {
    name: "Ngọa Long",
    username: "NgoaLong",
    initials: "NL",
    elo: 2486,
    games: 386,
    rate: 82,
    tone: "sage",
    change: 2,
  },
  {
    name: "Độc Cô Cầu Bại",
    username: "DocCoCauBai",
    initials: "ĐC",
    elo: 2412,
    games: 452,
    rate: 78,
    tone: "sand",
    change: 1,
  },
  {
    name: "Kỳ Vương",
    username: "KyVuong",
    initials: "KV",
    elo: 2358,
    games: 318,
    rate: 76,
    tone: "blue",
    change: -1,
  },
  {
    name: "Thiên Mã",
    username: "ThienMa",
    initials: "TM",
    elo: 2290,
    games: 296,
    rate: 74,
    tone: "rose",
    change: 3,
  },
  {
    name: "Bạch Hổ",
    username: "BachHo",
    initials: "BH",
    elo: 2216,
    games: 270,
    rate: 72,
    tone: "sage",
    change: 0,
  },
  {
    name: "Lâm Sơn",
    username: "LamSon",
    initials: "LS",
    elo: 2168,
    games: 241,
    rate: 70,
    tone: "sand",
    change: 2,
  },
  {
    name: "Thanh Phong",
    username: "ThanhPhong",
    initials: "TP",
    elo: 2082,
    games: 216,
    rate: 69,
    tone: "blue",
    change: 1,
  },
  {
    name: "Tĩnh Tâm",
    username: "TinhTam",
    initials: "TT",
    elo: 2040,
    games: 208,
    rate: 68,
    tone: "rose",
    change: -2,
  },
  {
    name: "Minh Anh",
    username: "MinhAnh",
    initials: "MA",
    elo: INITIAL_DEMO_ELO,
    games: 48,
    rate: 65,
    tone: "sage",
    change: 5,
  },
  {
    name: "Tiểu Tốt",
    username: "TieuTot",
    initials: "TT",
    elo: 1180,
    games: 62,
    rate: 54,
    tone: "sand",
    change: 2,
  },
  {
    name: "Minh Khải",
    username: "MinhKhai",
    initials: "MK",
    elo: 1120,
    games: 38,
    rate: 52,
    tone: "blue",
    change: 1,
  },
  {
    name: "Tân Kỳ",
    username: "TanKy",
    initials: "TK",
    elo: 1080,
    games: 24,
    rate: 50,
    tone: "rose",
    change: 0,
  },
];

export type GameRecord = {
  id: string;
  opponent: string;
  initials: string;
  elo: number;
  result: "win" | "draw" | "loss";
  change: number;
  date: string;
  day: string;
  time: string;
  duration: string;
  reason: string;
  tone: string;
};

export const gameHistory: GameRecord[] = [
  {
    id: "GD2048",
    opponent: "ThanhPhong",
    initials: "TP",
    elo: 1320,
    result: "win",
    change: 16,
    date: "Hôm nay",
    day: "2026-05-24",
    time: "14:32",
    duration: "12 phút",
    reason: "Chiếu bí",
    tone: "sage",
  },
  {
    id: "GD2047",
    opponent: "CoThuSaiGon",
    initials: "CT",
    elo: 1450,
    result: "loss",
    change: -12,
    date: "Hôm nay",
    day: "2026-05-24",
    time: "11:15",
    duration: "18 phút",
    reason: "Đầu hàng",
    tone: "sand",
  },
  {
    id: "GD2046",
    opponent: "TieuTot",
    initials: "TT",
    elo: 1180,
    result: "win",
    change: 14,
    date: "Hôm qua",
    day: "2026-05-23",
    time: "20:46",
    duration: "9 phút",
    reason: "Hết thời gian",
    tone: "blue",
  },
  {
    id: "GD2045",
    opponent: "BachMa",
    initials: "BM",
    elo: 1380,
    result: "draw",
    change: 2,
    date: "Hôm qua",
    day: "2026-05-23",
    time: "19:20",
    duration: "24 phút",
    reason: "Đồng ý hòa",
    tone: "rose",
  },
  {
    id: "GD2044",
    opponent: "LamSon",
    initials: "LS",
    elo: 1375,
    result: "win",
    change: 18,
    date: "22/05/2026",
    day: "2026-05-22",
    time: "16:08",
    duration: "15 phút",
    reason: "Đối thủ đầu hàng",
    tone: "sage",
  },
  {
    id: "GD2043",
    opponent: "ThienMa",
    initials: "TM",
    elo: 1490,
    result: "loss",
    change: -10,
    date: "18/05/2026",
    day: "2026-05-18",
    time: "21:32",
    duration: "16 phút",
    reason: "Chiếu bí",
    tone: "sand",
  },
  {
    id: "GD2042",
    opponent: "TinhTam",
    initials: "TT",
    elo: 1260,
    result: "win",
    change: 15,
    date: "12/05/2026",
    day: "2026-05-12",
    time: "10:05",
    duration: "11 phút",
    reason: "Hết nước đi",
    tone: "blue",
  },
];

export const resultLabels = { win: "Thắng", draw: "Hòa", loss: "Thua" };

export function getDemoRankings(elo: number) {
  return rankings
    .map((player) =>
      player.username === "MinhAnh" && Number.isFinite(elo)
        ? { ...player, elo: Math.max(0, Math.floor(elo)) }
        : player,
    )
    .sort((a, b) => b.elo - a.elo);
}

export type Piece = {
  id: string;
  side: Side;
  kind: string;
  label: PieceType;
  x: number;
  y: number;
};
export type ChessMove = {
  pieceId: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  notation: string;
  side: Side;
};

export function initialPieces(): Piece[] {
  const back: PieceType[] = ["Xe", "Mã", "Tượng", "Sĩ", "Tướng", "Sĩ", "Tượng", "Mã", "Xe"];
  return (["black", "red"] as Side[]).flatMap((side) => {
    const y = side === "red" ? 9 : 0;
    const pieces: Piece[] = back.map((label, x) => ({
      id: `${side}-${x}`,
      side,
      kind: pieceSymbol(side, label),
      label,
      x,
      y,
    }));
    [1, 7].forEach((x) =>
      pieces.push({
        id: `${side}-c${x}`,
        side,
        kind: pieceSymbol(side, "Pháo"),
        label: "Pháo",
        x,
        y: side === "red" ? 7 : 2,
      }),
    );
    [0, 2, 4, 6, 8].forEach((x) =>
      pieces.push({
        id: `${side}-p${x}`,
        side,
        kind: pieceSymbol(side, "Tốt"),
        label: "Tốt",
        x,
        y: side === "red" ? 6 : 3,
      }),
    );
    return pieces;
  });
}

const fenPieceTypes: Record<string, PieceType> = {
  k: "Tướng",
  a: "Sĩ",
  b: "Tượng",
  e: "Tượng",
  n: "Mã",
  h: "Mã",
  r: "Xe",
  c: "Pháo",
  p: "Tốt",
};

export function piecesFromFen(fen: string): Piece[] {
  const placement = fen.trim().split(/\s+/)[0];
  const rows = placement?.split("/") || [];
  if (rows.length !== 10) throw new Error("FEN bàn cờ cần có 10 hàng.");
  const pieces: Piece[] = [];
  rows.forEach((row, y) => {
    let x = 0;
    for (const code of row) {
      if (/^[1-9]$/.test(code)) {
        x += Number(code);
        continue;
      }
      const label = fenPieceTypes[code.toLowerCase()];
      if (!label || x > 8) throw new Error("FEN bàn cờ không hợp lệ.");
      const side: Side = code === code.toUpperCase() ? "red" : "black";
      pieces.push({
        id: `${side}-${x}-${y}`,
        side,
        kind: pieceSymbol(side, label),
        label,
        x,
        y,
      });
      x += 1;
    }
    if (x !== 9) throw new Error("Mỗi hàng FEN phải có đúng 9 cột.");
  });
  return pieces;
}

export const replayMoves: ChessMove[] = [
  {
    pieceId: "red-c7",
    fromX: 7,
    fromY: 7,
    toX: 4,
    toY: 7,
    notation: "P2–5",
    side: "red",
  },
  {
    pieceId: "black-7",
    fromX: 7,
    fromY: 0,
    toX: 6,
    toY: 2,
    notation: "M8.7",
    side: "black",
  },
  {
    pieceId: "red-7",
    fromX: 7,
    fromY: 9,
    toX: 6,
    toY: 7,
    notation: "M2.3",
    side: "red",
  },
  {
    pieceId: "black-8",
    fromX: 8,
    fromY: 0,
    toX: 7,
    toY: 0,
    notation: "X9–8",
    side: "black",
  },
  {
    pieceId: "red-8",
    fromX: 8,
    fromY: 9,
    toX: 7,
    toY: 9,
    notation: "X1–2",
    side: "red",
  },
  {
    pieceId: "black-p4",
    fromX: 4,
    fromY: 3,
    toX: 4,
    toY: 4,
    notation: "T5.1",
    side: "black",
  },
  {
    pieceId: "red-p4",
    fromX: 4,
    fromY: 6,
    toX: 4,
    toY: 5,
    notation: "T5.1",
    side: "red",
  },
  {
    pieceId: "black-c1",
    fromX: 1,
    fromY: 2,
    toX: 2,
    toY: 2,
    notation: "P2–3",
    side: "black",
  },
  {
    pieceId: "red-1",
    fromX: 1,
    fromY: 9,
    toX: 2,
    toY: 7,
    notation: "M8.7",
    side: "red",
  },
  {
    pieceId: "black-p2",
    fromX: 2,
    fromY: 3,
    toX: 2,
    toY: 4,
    notation: "T3.1",
    side: "black",
  },
  {
    pieceId: "red-c1",
    fromX: 1,
    fromY: 7,
    toX: 1,
    toY: 4,
    notation: "P8.3",
    side: "red",
  },
  {
    pieceId: "black-1",
    fromX: 1,
    fromY: 0,
    toX: 2,
    toY: 2,
    notation: "M2.3",
    side: "black",
  },
];
