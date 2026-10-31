/** Traditional Xiangqi faces. Notation and Vietnamese piece names stay separate. */
export const PIECE_SYMBOLS = {
  red: {
    Tướng: "帥",
    Sĩ: "仕",
    Tượng: "相",
    Mã: "傌",
    Xe: "俥",
    Pháo: "炮",
    Tốt: "兵",
  },
  black: {
    Tướng: "將",
    Sĩ: "士",
    Tượng: "象",
    Mã: "馬",
    Xe: "車",
    Pháo: "砲",
    Tốt: "卒",
  },
} as const;

export type PieceType = keyof typeof PIECE_SYMBOLS.red;

export function pieceSymbol(side: keyof typeof PIECE_SYMBOLS, type: PieceType) {
  return PIECE_SYMBOLS[side][type];
}
