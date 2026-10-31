import { useState } from "react";
import { Badge, Button, InputField, SelectField } from "@figma/astraui";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Calendar,
  CheckCircle,
  Flag,
  History as HistoryIcon,
  Medal,
  Minus,
  Pencil,
  Search,
  ShieldCheck,
  Sprout,
  Target,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { EmptyState, Heading, SectionTitle, UserAvatar } from "../components";
import { useApp } from "../context";
import { gameHistory, getDemoRankings, playerInitials, resultLabels } from "../data";
import { useExperience } from "../experience/Experience";
import { RankBadge, RankProgress } from "../rank-ui";
import { CULTIVATION_LAYERS } from "../ranks";
import { PodiumAvatar, type PodiumRank } from "../experience/PodiumAvatar";

export function History() {
  const { viewRecord, go, signedIn } = useApp();
  const { demoElo } = useExperience();
  const [filter, setFilter] = useState("all");
  const [range, setRange] = useState("all");
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(6);
  const records = gameHistory.filter(
    (game) =>
      (filter === "all" || game.result === filter) &&
      game.opponent.toLowerCase().includes(query.toLowerCase()) &&
      (range === "all" || game.day >= (range === "week" ? "2026-05-18" : "2026-05-01")),
  );
  return (
    <div className="page-stack history-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">MỖI VÁN CỜ, MỘT BÀI HỌC</div>
          <Heading level={1}>Hành trình trên bàn cờ</Heading>
          <div className="muted mt-xs">
            Nhìn lại những ván đã qua. Vững vàng cho nước cờ sắp tới.
          </div>
        </div>
        <Button variant="neutral" iconStart={<SwordsSmall />} onClick={() => go("rooms")}>
          Chơi một ván mới
        </Button>
      </div>
      <div className="history-stat-grid">
        {[
          {
            icon: Flag,
            label: "Tổng số trận",
            value: signedIn ? "48" : "0",
            tone: "blue",
            extra: "Một hành trình không ngừng tiến bộ",
          },
          {
            icon: Trophy,
            label: "Trận thắng",
            value: signedIn ? "31" : "0",
            tone: "sage",
            extra: "65% tỷ lệ chiến thắng",
          },
          {
            icon: Target,
            label: "Elo hiện tại",
            value: (signedIn ? demoElo : 1000).toLocaleString("vi-VN"),
            tone: "sand",
            extra: "+48 Elo trong tuần này",
          },
        ].map(({ icon: Icon, label, value, tone, extra }) => (
          <div className="surface history-stat" key={label}>
            <div className="between">
              <span className="muted">{label}</span>
              <span className={`quick-icon tone-${tone}`}>
                <Icon size={21} />
              </span>
            </div>
            <div className="history-stat-number">{value}</div>
            <div className="small muted">{extra}</div>
          </div>
        ))}
      </div>
      <section className="surface history-list">
        <div className="section-title">
          <Heading>Lịch sử ván đấu</Heading>
          <span className="small muted">{signedIn ? gameHistory.length : 0} ván gần đây</span>
        </div>
        <div className="history-filters">
          <div className="result-filters">
            {[
              { id: "all", label: "Tất cả" },
              { id: "win", label: "Thắng" },
              { id: "draw", label: "Hòa" },
              { id: "loss", label: "Thua" },
            ].map((option) => (
              <Button
                variant="subtle"
                size="small"
                key={option.id}
                className={`filter-chip ${filter === option.id ? "active" : ""}`}
                onClick={() => setFilter(option.id)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <div className="history-filter-inputs">
            <InputField
              prefix={<Search size={16} />}
              aria-label="Tìm đối thủ"
              placeholder="Tìm đối thủ..."
              value={query}
              onChange={setQuery}
            />
            <SelectField
              value={range}
              onChange={setRange}
              options={[
                { value: "all", label: "Tất cả thời gian" },
                { value: "week", label: "7 ngày gần đây" },
                { value: "month", label: "Tháng này" },
              ]}
            />
          </div>
        </div>
        {!signedIn ? (
          <EmptyState
            icon={<HistoryIcon size={28} />}
            title="Những ván cờ hay đang ở phía trước"
            description="Đăng nhập để lưu lại ván đấu và xem mình đã tiến bộ như thế nào."
            action="Đăng nhập"
            onAction={() => go("login")}
          />
        ) : records.length === 0 ? (
          <EmptyState
            title="Chưa có ván đấu phù hợp"
            description="Thử thay đổi bộ lọc hoặc bắt đầu một ván cờ mới."
            action="Xóa bộ lọc"
            onAction={() => {
              setFilter("all");
              setRange("all");
              setQuery("");
            }}
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table history-table">
                <thead>
                  <tr>
                    <th>Đối thủ</th>
                    <th>Kết quả</th>
                    <th>Thay đổi Elo</th>
                    <th>Thời gian</th>
                    <th>Lý do kết thúc</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {records.slice(0, visible).map((game) => (
                    <tr key={game.id}>
                      <td>
                        <div className="inline">
                          <UserAvatar initials={game.initials} tone={game.tone} elo={game.elo} />
                          <div>
                            <div className="player-name">{game.opponent}</div>
                            <div className="small muted">
                              {game.elo.toLocaleString("vi-VN")} Elo{" "}
                              <span className="meta-dot">·</span>#{game.id}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={`result-tag ${game.result}`}>
                          {resultLabels[game.result]}
                        </span>
                      </td>
                      <td>
                        <span className={`elo-change ${game.change > 0 ? "positive" : "negative"}`}>
                          {game.change > 0 ? "+" : ""}
                          {game.change}
                        </span>
                      </td>
                      <td>
                        <div>
                          {game.date}, {game.time}
                        </div>
                        <div className="small muted">{game.duration}</div>
                      </td>
                      <td className="muted">{game.reason}</td>
                      <td>
                        <Button
                          variant="neutral"
                          size="small"
                          iconEnd={<ArrowUpRight size={15} />}
                          onClick={() => viewRecord(game)}
                        >
                          Xem lại
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {records.length > visible && (
              <div className="load-more">
                <Button variant="neutral" onClick={() => setVisible((n) => n + 6)}>
                  Xem thêm ván đấu
                </Button>
              </div>
            )}
          </>
        )}
      </section>
      <div className="history-note">
        <ShieldCheck size={16} />
        <span>Thắng thua là kết quả. Tiến bộ mới là hành trình.</span>
      </div>
    </div>
  );
}

function SwordsSmall() {
  return <Flag size={16} />;
}

export function Leaderboard() {
  const { username, signedIn, go, openModal } = useApp();
  const { demoElo } = useExperience();
  const players = getDemoRankings(demoElo);
  const myPosition = players.findIndex((player) => player.username === "MinhAnh") + 1;
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(8);
  const filtered = players.filter((p) =>
    `${p.name} ${p.username} ${p.username === "MinhAnh" && signedIn ? username : ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <div className="page-stack leaderboard-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">VƯƠN TẦM KỲ THỦ</div>
          <Heading level={1}>Bảng Phong Thần</Heading>
          <div className="muted mt-xs">Tôn vinh bản lĩnh. Truyền cảm hứng cho từng nước cờ.</div>
        </div>
        <div className="ranking-season">
          <span className="quick-icon tone-sand">
            <Trophy size={22} />
          </span>
          <div>
            <div className="player-name">Mùa hè 2026</div>
            <div className="small muted">Elo và cảnh giới demo</div>
          </div>
        </div>
      </div>
      {!query && (
        <div className="podium-grid" aria-label="Vinh danh ba kỳ thủ dẫn đầu">
          {players.slice(0, 3).map((player, i) => {
            const rank = (i + 1) as PodiumRank;
            const current = player.username === "MinhAnh" && signedIn;
            return (
              <section
                key={player.username}
                className={`podium-card podium-${rank}`}
                aria-label={`Top ${rank} · ${player.name}`}
              >
                <Badge label={`Top ${rank}`} variant="secondary" className="podium-place" />
                <PodiumAvatar
                  rank={rank}
                  name={current ? username : player.name}
                  initials={player.initials}
                  tone={player.tone}
                  avatarUrl={player.avatarUrl}
                  current={current}
                />
                <Heading>{current ? username : player.username}</Heading>
                <div className="muted small">{current ? username : player.name}</div>
                <RankBadge elo={player.elo} compact />
                <div className="podium-elo">
                  {player.elo.toLocaleString("vi-VN")}
                  <span>Elo</span>
                </div>
                <div className="podium-meta">
                  <span>{player.games} trận</span>
                  <span className="meta-dot">·</span>
                  <span>{player.rate}% thắng</span>
                </div>
              </section>
            );
          })}
        </div>
      )}
      {signedIn && (
        <div className="your-rank">
          <div className="your-rank-position">{String(myPosition).padStart(2, "0")}</div>
          <UserAvatar initials={playerInitials(username)} tone="sage" current />
          <div className="grow">
            <div className="inline">
              <span className="player-name">{username}</span>
              <Badge label="Bạn" variant="brand" />
            </div>
            <div className="small muted">
              <RankBadge elo={demoElo} /> · Dữ liệu demo, không đồng bộ máy chủ.
            </div>
          </div>
          <span className="your-rank-trend">
            <TrendingUp size={16} />5 bậc
          </span>
          <div className="your-rank-elo">
            {demoElo.toLocaleString("vi-VN")} <span>Elo</span>
          </div>
          <Button
            variant="neutral"
            size="small"
            iconEnd={<ArrowRight size={14} />}
            onClick={() => go("profile")}
          >
            Hồ sơ của tôi
          </Button>
        </div>
      )}
      <div className="between realm-explainer">
        <span className="small muted">
          13 cảnh giới · {CULTIVATION_LAYERS} tầng mỗi bậc · Ngưỡng Elo riêng cho bản demo
        </span>
        <Button
          variant="subtle"
          size="small"
          iconEnd={<ArrowRight size={14} />}
          onClick={() => openModal("ranks")}
        >
          Lộ trình tu luyện
        </Button>
      </div>
      <section className="surface ranking-table-panel">
        <div className="section-title">
          <div>
            <Heading>Những kỳ thủ hàng đầu</Heading>
            <div className="muted small mt-xs">Cùng học hỏi từ cộng đồng Kỳ Tiên Hội.</div>
          </div>
          <div className="ranking-search">
            <InputField
              aria-label="Tìm kỳ thủ"
              prefix={<Search size={16} />}
              placeholder="Tìm tên kỳ thủ..."
              value={query}
              onChange={setQuery}
            />
          </div>
        </div>
        {filtered.length ? (
          <>
            <div className="table-wrap">
              <table className="data-table ranking-table">
                <thead>
                  <tr>
                    <th>Thứ hạng</th>
                    <th>Kỳ thủ</th>
                    <th>Điểm Elo</th>
                    <th>Số trận</th>
                    <th>Tỷ lệ thắng</th>
                    <th>Biến động</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, visible).map((player) => {
                    const rank = players.findIndex((p) => p.username === player.username) + 1;
                    const current = player.username === "MinhAnh" && signedIn;
                    return (
                      <tr
                        key={player.username}
                        className={`${current ? "current-user-row" : ""} ${
                          rank <= 3 ? "vip-ranked-row" : ""
                        }`}
                      >
                        <td>
                          <span className={`table-rank table-rank-${rank}`}>
                            {rank <= 3 ? (
                              <span className="inline">
                                <Medal size={17} />
                                {rank}
                              </span>
                            ) : (
                              String(rank).padStart(2, "0")
                            )}
                          </span>
                        </td>
                        <td>
                          <div className="inline">
                            {rank >= 1 && rank <= 3 ? (
                              <PodiumAvatar
                                rank={rank as PodiumRank}
                                name={current ? username : player.name}
                                initials={player.initials}
                                tone={player.tone}
                                avatarUrl={player.avatarUrl}
                                current={current}
                                compact
                              />
                            ) : (
                              <UserAvatar
                                initials={player.initials}
                                tone={player.tone}
                                elo={player.elo}
                                current={current}
                              />
                            )}
                            <div>
                              <div className="player-name">
                                {current ? username : player.username}
                                {current && <Badge label="Bạn" variant="brand" />}
                              </div>
                              <RankBadge elo={player.elo} compact />
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="ranking-elo-value">
                            {player.elo.toLocaleString("vi-VN")}
                          </span>
                        </td>
                        <td>{player.games}</td>
                        <td>
                          <div className="win-rate-cell">
                            <span>{player.rate}%</span>
                            <div className="win-rate-bar">
                              <span style={{ width: `${player.rate}%` }} />
                            </div>
                          </div>
                        </td>
                        <td>
                          <span
                            className={`rank-change ${
                              player.change > 0 ? "up" : player.change < 0 ? "down" : ""
                            }`}
                          >
                            {player.change > 0 ? (
                              <ArrowUp size={14} />
                            ) : player.change < 0 ? (
                              <ArrowDown size={14} />
                            ) : (
                              <Minus size={14} />
                            )}
                            {Math.abs(player.change) || "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {filtered.length > visible && (
              <div className="load-more">
                <Button variant="neutral" onClick={() => setVisible((n) => n + 8)}>
                  Tải thêm kỳ thủ
                </Button>
              </div>
            )}
          </>
        ) : (
          <EmptyState
            title="Chưa tìm thấy kỳ thủ"
            description="Hãy thử một tên khác hoặc kiểm tra lại chính tả."
            action="Xem tất cả kỳ thủ"
            onAction={() => setQuery("")}
          />
        )}
      </section>
    </div>
  );
}

export function Profile() {
  const { username, profileTone, go, openModal, viewRecord, signedIn } = useApp();
  const { demoElo, avatar } = useExperience();
  const [empty, setEmpty] = useState(!signedIn);
  const profileElo = empty ? 1000 : demoElo;
  const position =
    getDemoRankings(demoElo).findIndex((player) => player.username === "MinhAnh") + 1;
  return (
    <div className="page-stack profile-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">HÀNH TRÌNH CỦA RIÊNG BẠN</div>
          <Heading level={1}>Hồ sơ kỳ thủ</Heading>
          <div className="muted mt-xs">Mỗi ngày một nước cờ tốt hơn.</div>
        </div>
        <div className="inline profile-actions">
          <Button
            variant="neutral"
            iconStart={<Pencil size={16} />}
            onClick={() => openModal("edit")}
          >
            Chỉnh sửa hồ sơ
          </Button>
        </div>
      </div>
      <section className="surface profile-hero">
        <div className="profile-hero-decoration" />
        <div className="profile-identity">
          <UserAvatar
            initials={playerInitials(username)}
            tone={profileTone}
            className="profile-large-avatar"
            elo={profileElo}
            current={signedIn && !empty}
          />
          <div>
            <div className="inline">
              <Heading level={1}>{username}</Heading>
              <ShieldCheck size={20} className="verified-icon" />
            </div>
            <div className="profile-level">
              <span className="level-dot" />
              <RankBadge elo={profileElo} />
            </div>
            <div className="small muted profile-joined">
              <Calendar size={13} />
              Tham gia từ tháng 3, 2026
            </div>
            <div className="tiny muted mt-xs">
              {avatar && !empty
                ? "Ảnh lưu cục bộ · chưa tải lên máy chủ"
                : "Hồ sơ và cảnh giới demo"}
            </div>
          </div>
        </div>
        <div className="profile-hero-stats">
          <div>
            <span className="profile-stat-number">{profileElo.toLocaleString("vi-VN")}</span>
            <span className="muted">Điểm Elo</span>
          </div>
          <div>
            <span className="profile-stat-number">{empty ? "0" : "48"}</span>
            <span className="muted">Tổng số trận</span>
          </div>
          <div>
            <span className="profile-stat-number">
              {empty ? "—" : String(position).padStart(2, "0")}
            </span>
            <span className="muted">Hạng cộng đồng</span>
          </div>
        </div>
      </section>
      <section className="surface profile-cultivation">
        <SectionTitle
          title="Hành trình tu luyện"
          action="Lộ trình 13 cảnh giới"
          onAction={() => openModal("ranks")}
        />
        <RankProgress elo={profileElo} />
      </section>
      <div className="profile-content-grid">
        <section className="surface profile-performance">
          <SectionTitle title="Thành tích trên bàn cờ" />
          <div className="performance-content">
            <div className={`donut-chart ${empty ? "donut-empty" : ""}`}>
              <div>
                <strong>
                  {empty ? "0" : "65"}
                  <span>%</span>
                </strong>
                <span>Tỷ lệ thắng</span>
              </div>
            </div>
            <div className="performance-stats">
              {[
                { label: "Thắng", value: 31, percent: 65, cls: "win" },
                { label: "Hòa", value: 8, percent: 17, cls: "draw" },
                { label: "Thua", value: 9, percent: 18, cls: "loss" },
              ].map((stat) => (
                <div className="performance-row" key={stat.cls}>
                  <span className={`performance-dot ${stat.cls}`} />
                  <span className="grow">{stat.label}</span>
                  <strong>{empty ? "0" : stat.value}</strong>
                  <span className="muted small">{empty ? "0" : stat.percent}%</span>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="surface weekly-performance">
          <SectionTitle title="Nhịp cờ trong tuần" />
          <div className="weekly-chart">
            {[3, 5, 2, 6, 4, 7, 4].map((n, i) => (
              <div className="weekly-column" key={i}>
                <span className="weekly-bar-value">{empty ? "0" : n}</span>
                <div
                  className={`weekly-bar ${i === 5 ? "weekly-highlight" : ""}`}
                  style={{ height: `${empty ? 3 : n * 12}%` }}
                />
                <span className="small muted">{["T2", "T3", "T4", "T5", "T6", "T7", "CN"][i]}</span>
              </div>
            ))}
          </div>
          <div className="weekly-caption">
            <TrendingUp size={15} />
            {empty ? "Ván đầu tiên đang chờ bạn." : "Chơi đều đặn, tiến bộ mỗi ngày."}
          </div>
        </section>
      </div>
      {empty ? (
        <section className="surface">
          <EmptyState
            icon={<Sprout size={28} />}
            title="Ván cờ đầu tiên đang chờ bạn"
            description="Mọi kỳ thủ đều bắt đầu từ một nước đi. Thử một ván với máy để làm quen nhé!"
            action="Chơi ván đầu tiên"
            onAction={() => go("ai")}
          />
        </section>
      ) : (
        <>
          <section className="surface profile-achievements">
            <SectionTitle title="Dấu ấn kỳ thủ" />
            <div className="achievement-grid">
              {[
                {
                  icon: Flag,
                  title: "Nước cờ đầu tiên",
                  detail: "Hoàn thành ván đầu tiên",
                  tone: "sage",
                },
                {
                  icon: Trophy,
                  title: "Bản lĩnh chiến thắng",
                  detail: "Giành 25 chiến thắng",
                  tone: "sand",
                },
                {
                  icon: Target,
                  title: "Vững bước Trúc Cơ",
                  detail: "Chạm mốc 1.200 Elo",
                  tone: "blue",
                },
              ].map(({ icon: Icon, title, detail, tone }) => (
                <div className="achievement" key={title}>
                  <span className={`achievement-icon tone-${tone}`}>
                    <Icon size={25} strokeWidth={1.5} />
                  </span>
                  <div>
                    <div className="player-name">{title}</div>
                    <div className="small muted">{detail}</div>
                  </div>
                  <CheckCircle size={15} className="achievement-check" />
                </div>
              ))}
            </div>
          </section>
          <section className="surface">
            <SectionTitle
              title="Những ván cờ gần đây"
              action="Xem toàn bộ lịch sử"
              onAction={() => go("history")}
            />
            <div className="profile-recent">
              {gameHistory.slice(0, 3).map((game) => (
                <div className="profile-recent-row" key={game.id}>
                  <UserAvatar initials={game.initials} tone={game.tone} elo={game.elo} />
                  <div className="grow">
                    <div className="player-name">{game.opponent}</div>
                    <span className="small muted">
                      {game.date}, {game.time}
                    </span>
                  </div>
                  <span className={`result-tag ${game.result}`}>{resultLabels[game.result]}</span>
                  <span className={`elo-change ${game.change > 0 ? "positive" : "negative"}`}>
                    {game.change > 0 ? "+" : ""}
                    {game.change} Elo
                  </span>
                  <Button variant="neutral" size="small" onClick={() => viewRecord(game)}>
                    Xem lại
                    <ArrowUpRight size={14} />
                  </Button>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      <div className="profile-state-toggle">
        <Button variant="subtle" size="small" onClick={() => setEmpty((value) => !value)}>
          {empty ? "Xem hồ sơ có trận đấu" : "Xem trạng thái kỳ thủ mới"}
        </Button>
        <span className="small muted">Trạng thái minh họa</span>
      </div>
    </div>
  );
}
