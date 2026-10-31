/** Product-specific demo thresholds, not an official Xiangqi rating standard. */
export const CULTIVATION_RANKS = [
  { name: "Phàm Nhân", minElo: 0 },
  { name: "Luyện Khí", minElo: 1000 },
  { name: "Trúc Cơ", minElo: 1200 },
  { name: "Kim Đan", minElo: 1400 },
  { name: "Nguyên Anh", minElo: 1600 },
  { name: "Hóa Thần", minElo: 1800 },
  { name: "Luyện Hư", minElo: 2000 },
  { name: "Hợp Thể", minElo: 2200 },
  { name: "Đại Thừa", minElo: 2400 },
  { name: "Độ Kiếp", minElo: 2600 },
  { name: "Chân Tiên", minElo: 2800 },
  { name: "Kim Tiên", minElo: 3000 },
  { name: "Tiên Đế", minElo: 3200 },
] as const;

export const CULTIVATION_LAYERS = 3;
export const INITIAL_DEMO_ELO = 1250;

export function getCultivationRank(value: number) {
  const elo = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  let index = 0;
  CULTIVATION_RANKS.forEach((rank, i) => {
    if (elo >= rank.minElo) index = i;
  });
  const realm = CULTIVATION_RANKS[index];
  const next = CULTIVATION_RANKS[index + 1];
  const progress = next
    ? Math.min(100, Math.max(0, ((elo - realm.minElo) / (next.minElo - realm.minElo)) * 100))
    : 100;
  const layer = next
    ? Math.min(CULTIVATION_LAYERS, Math.floor((progress / 100) * CULTIVATION_LAYERS) + 1)
    : Math.min(CULTIVATION_LAYERS, Math.floor((elo - realm.minElo) / 100) + 1);
  return {
    ...realm,
    index,
    elo,
    next,
    progress,
    layer,
    remaining: next ? Math.max(0, next.minElo - elo) : 0,
    label: `${realm.name} · tầng ${layer}`,
  };
}
