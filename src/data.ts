import { pieceSymbol, type PieceType } from "./chess/pieces";

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
  roomCode?: string;
  name: string;
  host: string;
  ownedByMe?: boolean;
  initials: string;
  elo?: number | null;
  seconds: number;
  players: number;
  private?: boolean;
  playing?: boolean;
  spectators: boolean;
  tone: string;
  player2Name?: string | null;
  player2Elo?: number | null;
};

export function mergeRoomSummary(room: Room, summary: Record<string, unknown>): Room {
  const hostName = typeof summary.host_name === "string" ? summary.host_name : room.host;
  const status = summary.status;
  return {
    ...room,
    roomCode: typeof summary.room_code === "string" ? summary.room_code : room.roomCode,
    name:
      typeof summary.room_name === "string"
        ? summary.room_name
        : typeof summary.name === "string"
          ? summary.name
          : room.name,
    host: hostName,
    initials: hostName === room.host ? room.initials : playerInitials(hostName),
    elo:
      summary.host_elo === null
        ? null
        : typeof summary.host_elo === "number"
          ? summary.host_elo
          : room.elo,
    player2Name:
      summary.player2_name === null
        ? null
        : typeof summary.player2_name === "string"
          ? summary.player2_name
          : (room.player2Name ?? null),
    player2Elo:
      summary.player2_elo === null
        ? null
        : typeof summary.player2_elo === "number"
          ? summary.player2_elo
          : (room.player2Elo ?? null),
    players: typeof summary.player_count === "number" ? summary.player_count : room.players,
    private: typeof summary.is_public === "boolean" ? !summary.is_public : room.private,
    playing:
      status === "playing"
        ? true
        : status === "waiting" || status === "finished"
          ? false
          : room.playing,
    spectators:
      typeof summary.allow_spectators === "boolean" ? summary.allow_spectators : room.spectators,
  };
}

export type GameRecord = {
  id: number;
  match_key: string;
  room_id: number;
  room_uuid: string;
  round_number: number;
  room_name: string;
  red_player: string;
  black_player: string;
  red_user_id: number | null;
  black_user_id: number | null;
  result: string;
  reason: string | null;
  winner: "w" | "b" | null;
  notation: string;
  final_fen: string;
  finished_at: string;
  red_elo_change: number;
  black_elo_change: number;
};

export type RankedPlayer = {
  rank: number;
  user_id: number;
  username: string | null;
  display_name: string;
  elo: number;
  games_played: number;
  wins: number;
  draws: number;
  losses: number;
  win_rate: number;
};

export type PlayerStats = {
  user_id: number;
  display_name: string;
  username: string | null;
  elo: number;
  games_played: number;
  wins: number;
  draws: number;
  losses: number;
  win_rate: number;
  rank: number | null;
};

export type CommunitySummary = {
  registered_players: number;
  open_public_rooms: number;
  completed_public_games: number;
};

export const resultLabels: Record<"win" | "draw" | "loss", string> = {
  win: "Thắng",
  draw: "Hòa",
  loss: "Thua",
};

export function matchResultForUser(match: GameRecord, userId: number): "win" | "draw" | "loss" {
  if (match.winner === null) return "draw";
  const side = match.red_user_id === userId ? "w" : match.black_user_id === userId ? "b" : null;
  if (!side) return "draw";
  return match.winner === side ? "win" : "loss";
}

export function opponentNameForUser(match: GameRecord, userId: number): string {
  if (match.red_user_id === userId) return match.black_player;
  if (match.black_user_id === userId) return match.red_player;
  return `${match.red_player} — ${match.black_player}`;
}

export function eloChangeForUser(match: GameRecord, userId: number): number {
  if (match.red_user_id === userId) return match.red_elo_change;
  if (match.black_user_id === userId) return match.black_elo_change;
  return 0;
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

export function parseReplayMoves(notation: string): ChessMove[] {
  const pieces = initialPieces();
  const replay: ChessMove[] = [];
  let side: Side = "red";
  for (const token of notation.trim().split(/\s+/).filter(Boolean)) {
    if (/^\d+\.(?:\.\.)?$/.test(token)) continue;
    const coordinates = token.match(/^([a-i])([0-9])-([a-i])([0-9])$/);
    if (!coordinates) throw new Error("Biên bản nước đi không hợp lệ.");
    const [, fromFile, fromRank, toFile, toRank] = coordinates;
    const fromX = fromFile.charCodeAt(0) - 97;
    const fromY = Number(fromRank);
    const toX = toFile.charCodeAt(0) - 97;
    const toY = Number(toRank);
    const piece = pieces.find((candidate) => candidate.x === fromX && candidate.y === fromY);
    if (!piece || piece.side !== side || (fromX === toX && fromY === toY)) {
      throw new Error("Biên bản nước đi không hợp lệ.");
    }
    replay.push({
      pieceId: piece.id,
      fromX,
      fromY,
      toX,
      toY,
      notation: token,
      side,
    });
    const nextPieces = pieces
      .filter(
        (candidate) => candidate.id === piece.id || candidate.x !== toX || candidate.y !== toY,
      )
      .map((candidate) =>
        candidate.id === piece.id ? { ...candidate, x: toX, y: toY } : candidate,
      );
    pieces.splice(0, pieces.length, ...nextPieces);
    side = side === "red" ? "black" : "red";
  }
  return replay;
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
