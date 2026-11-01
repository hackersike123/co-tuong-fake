import { useMemo, useState } from "react";
import { Badge, Button, InputField, SelectField } from "@figma/astraui";
import {
  ArrowRight,
  ArrowUpRight,
  Calendar,
  Flag,
  History as HistoryIcon,
  Medal,
  Search,
  ShieldCheck,
  Swords,
  Target,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { EmptyState, Heading, SectionTitle, UserAvatar } from "../components";
import { useApp } from "../context";
import {
  eloChangeForUser,
  matchResultForUser,
  opponentNameForUser,
  playerInitials,
  resultLabels,
} from "../data";
import { useExperience } from "../experience/Experience";
import { intlLocale } from "../i18n-core";
import { useLanguage } from "../i18n";
import { PodiumAvatar, type PodiumRank } from "../experience/PodiumAvatar";
import { RankBadge, RankProgress } from "../rank-ui";
import { CULTIVATION_LAYERS } from "../ranks";

function formatDate(value: string, locale: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Không rõ thời gian" : date.toLocaleString(locale);
}

function getRangeStart(range: string): number | null {
  const now = new Date();
  if (range === "week") now.setDate(now.getDate() - 7);
  else if (range === "month") now.setDate(1);
  else return null;
  now.setHours(0, 0, 0, 0);
  return now.getTime();
}

export function History() {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const { viewRecord, go, signedIn, currentUser, myMatches, playerStats } = useApp();
  const [filter, setFilter] = useState("all");
  const [range, setRange] = useState("all");
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(10);
  const records = useMemo(() => {
    if (!currentUser) return [];
    const normalizedQuery = query.trim().toLocaleLowerCase(locale);
    const rangeStart = getRangeStart(range);
    return myMatches.filter((match) => {
      const result = matchResultForUser(match, currentUser.id);
      const opponent = opponentNameForUser(match, currentUser.id).toLocaleLowerCase(locale);
      const finishedAt = new Date(match.finished_at).getTime();
      return (
        (filter === "all" || result === filter) &&
        opponent.includes(normalizedQuery) &&
        (rangeStart === null || (Number.isFinite(finishedAt) && finishedAt >= rangeStart))
      );
    });
  }, [currentUser, filter, myMatches, query, range, locale]);
  const weeklyChange = currentUser
    ? myMatches
        .filter((match) => {
          const age = Date.now() - new Date(match.finished_at).getTime();
          return age >= 0 && age <= 7 * 24 * 60 * 60 * 1000;
        })
        .reduce((sum, match) => sum + eloChangeForUser(match, currentUser.id), 0)
    : 0;
  const stats = [
    {
      icon: Flag,
      label: "Tổng số trận",
      value: playerStats?.games_played ?? 0,
      tone: "blue",
      extra: "Các trận đã hoàn tất và lưu trên máy chủ",
    },
    {
      icon: Trophy,
      label: "Trận thắng",
      value: playerStats?.wins ?? 0,
      tone: "sage",
      extra: `${(playerStats?.win_rate ?? 0).toFixed(1)}% tỷ lệ chiến thắng`,
    },
    {
      icon: Target,
      label: "Elo hiện tại",
      value: playerStats?.elo.toLocaleString(locale) ?? "—",
      tone: "sand",
      extra: `${weeklyChange > 0 ? "+" : ""}${weeklyChange} Elo trong 7 ngày`,
    },
  ];
  return (
    <div className="page-stack history-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">MỖI VÁN CỜ, MỘT BÀI HỌC</div>
          <Heading level={1}>Hành trình trên bàn cờ</Heading>
          <div className="muted mt-xs">Lịch sử chỉ hiển thị các trận đã được máy chủ lưu.</div>
        </div>
        <Button variant="neutral" iconStart={<Swords size={16} />} onClick={() => go("rooms")}>
          Chơi một ván mới
        </Button>
      </div>
      <div className="history-stat-grid">
        {stats.map(({ icon: Icon, label, value, tone, extra }) => (
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
          <span className="small muted">
            {signedIn ? `${myMatches.length} ván đã lưu` : "Cần đăng nhập"}
          </span>
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
            title="Đăng nhập để xem lịch sử của bạn"
            description="Chỉ các trận trực tuyến được lưu trên máy chủ mới được tính vào lịch sử và Elo."
            action="Đăng nhập"
            onAction={() => go("login")}
          />
        ) : records.length === 0 ? (
          <EmptyState
            title={myMatches.length ? "Chưa có ván đấu phù hợp" : "Chưa có ván đấu được lưu"}
            description={
              myMatches.length
                ? "Thử thay đổi bộ lọc hoặc bắt đầu một ván cờ mới."
                : "Hoàn tất một ván trực tuyến giữa hai tài khoản để tạo lịch sử thật."
            }
            action={myMatches.length ? "Xóa bộ lọc" : "Tìm đối thủ"}
            onAction={() => {
              if (myMatches.length) {
                setFilter("all");
                setRange("all");
                setQuery("");
              } else go("rooms");
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
                    <th>Phòng</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {records.slice(0, visible).map((match) => {
                    const opponent = opponentNameForUser(match, currentUser!.id);
                    const result = matchResultForUser(match, currentUser!.id);
                    const change = eloChangeForUser(match, currentUser!.id);
                    return (
                      <tr key={match.match_key}>
                        <td>
                          <div className="inline">
                            <UserAvatar initials={playerInitials(opponent)} />
                            <div>
                              <div className="player-name">{opponent}</div>
                              <div className="small muted">Trận #{match.id}</div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`result-tag ${result}`}>{resultLabels[result]}</span>
                        </td>
                        <td>
                          <span
                            className={`elo-change ${change > 0 ? "positive" : change < 0 ? "negative" : ""}`}
                          >
                            {change > 0 ? "+" : ""}
                            {change} Elo
                          </span>
                        </td>
                        <td>{formatDate(match.finished_at, locale)}</td>
                        <td className="muted">{match.room_name}</td>
                        <td>
                          <Button
                            variant="neutral"
                            size="small"
                            iconEnd={<ArrowUpRight size={15} />}
                            onClick={() => viewRecord(match)}
                          >
                            Xem lại
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {records.length > visible && (
              <div className="load-more">
                <Button variant="neutral" onClick={() => setVisible((count) => count + 10)}>
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

export function Leaderboard() {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const { signedIn, currentUser, playerStats, leaderboard, communitySummary, go, openModal } =
    useApp();
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(10);
  const normalizedQuery = query.trim().toLocaleLowerCase(locale);
  const players = useMemo(
    () =>
      leaderboard.filter((player) =>
        `${player.display_name} ${player.username ?? ""}`
          .toLocaleLowerCase(locale)
          .includes(normalizedQuery),
      ),
    [leaderboard, locale, normalizedQuery],
  );
  return (
    <div className="page-stack leaderboard-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">VƯƠN TẦM KỲ THỦ</div>
          <Heading level={1}>Bảng Phong Thần</Heading>
          <div className="muted mt-xs">
            Xếp hạng được tính từ điểm Elo của tài khoản và kết quả trận đã lưu.
          </div>
        </div>
        <div className="ranking-season">
          <span className="quick-icon tone-sand">
            <Trophy size={22} />
          </span>
          <div>
            <div className="player-name">Bảng xếp hạng hiện tại</div>
            <div className="small muted">
              {communitySummary?.registered_players ?? "—"} tài khoản
            </div>
          </div>
        </div>
      </div>
      {!normalizedQuery && players.length >= 3 && (
        <div className="podium-grid" aria-label="Ba kỳ thủ đứng đầu">
          {players.slice(0, 3).map((player, index) => {
            const rank = (index + 1) as PodiumRank;
            const current = player.user_id === currentUser?.id;
            return (
              <section
                key={player.user_id}
                className={`podium-card podium-${rank}`}
                aria-label={`Hạng ${rank} · ${player.display_name}`}
              >
                <Badge label={`Hạng ${rank}`} variant="secondary" className="podium-place" />
                <PodiumAvatar
                  rank={rank}
                  name={player.display_name}
                  initials={playerInitials(player.display_name)}
                  tone="sage"
                  current={current}
                />
                <Heading>{player.display_name}</Heading>
                <div className="muted small">
                  {player.username ? `@${player.username}` : "Tài khoản kỳ thủ"}
                </div>
                <RankBadge elo={player.elo} compact />
                <div className="podium-elo">
                  {player.elo.toLocaleString(locale)}
                  <span>Elo</span>
                </div>
                <div className="podium-meta">
                  <span>{player.games_played} trận</span>
                  <span className="meta-dot">·</span>
                  <span>{player.win_rate.toFixed(1)}% thắng</span>
                </div>
              </section>
            );
          })}
        </div>
      )}
      {signedIn && playerStats && (
        <div className="your-rank">
          <div className="your-rank-position">
            {playerStats.rank ? String(playerStats.rank).padStart(2, "0") : "—"}
          </div>
          <UserAvatar
            initials={playerInitials(playerStats.display_name)}
            tone="sage"
            current
            elo={playerStats.elo}
          />
          <div className="grow">
            <div className="inline">
              <span className="player-name">{playerStats.display_name}</span>
              <Badge label="Bạn" variant="brand" />
            </div>
            <div className="small muted">
              <RankBadge elo={playerStats.elo} /> · {playerStats.games_played} trận đã lưu
            </div>
          </div>
          <span className="your-rank-trend">
            <TrendingUp size={16} />
            {playerStats.win_rate.toFixed(1)}% thắng
          </span>
          <div className="your-rank-elo">
            {playerStats.elo.toLocaleString(locale)} <span>Elo</span>
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
          {`13 cảnh giới · ${CULTIVATION_LAYERS} tầng mỗi bậc · Ngưỡng riêng của Kỳ Tiên Hội`}
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
            <div className="muted small mt-xs">
              {`${leaderboard.length} tài khoản có dữ liệu trên máy chủ.`}
            </div>
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
        {players.length ? (
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
                    <th>Thắng / hòa / thua</th>
                  </tr>
                </thead>
                <tbody>
                  {players.slice(0, visible).map((player) => {
                    const current = player.user_id === currentUser?.id;
                    return (
                      <tr
                        key={player.user_id}
                        className={`${current ? "current-user-row" : ""} ${player.rank <= 3 ? "vip-ranked-row" : ""}`}
                      >
                        <td>
                          <span className={`table-rank table-rank-${player.rank}`}>
                            {player.rank <= 3 ? (
                              <span className="inline">
                                <Medal size={17} />
                                {player.rank}
                              </span>
                            ) : (
                              String(player.rank).padStart(2, "0")
                            )}
                          </span>
                        </td>
                        <td>
                          <div className="inline">
                            <UserAvatar
                              initials={playerInitials(player.display_name)}
                              tone="sage"
                              elo={player.elo}
                              current={current}
                            />
                            <div>
                              <div className="player-name">
                                {player.display_name}
                                {current && <Badge label="Bạn" variant="brand" />}
                              </div>
                              <RankBadge elo={player.elo} compact />
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="ranking-elo-value">
                            {player.elo.toLocaleString(locale)}
                          </span>
                        </td>
                        <td>{player.games_played}</td>
                        <td>
                          <div className="win-rate-cell">
                            <span>{player.win_rate.toFixed(1)}%</span>
                            <div className="win-rate-bar">
                              <span
                                style={{ width: `${Math.max(0, Math.min(100, player.win_rate))}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td>
                          {player.wins} / {player.draws} / {player.losses}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {players.length > visible && (
              <div className="load-more">
                <Button variant="neutral" onClick={() => setVisible((count) => count + 10)}>
                  Tải thêm kỳ thủ
                </Button>
              </div>
            )}
          </>
        ) : (
          <EmptyState
            title={normalizedQuery ? "Chưa tìm thấy kỳ thủ" : "Chưa có dữ liệu xếp hạng"}
            description={
              normalizedQuery
                ? "Hãy thử tên khác."
                : "Tài khoản sẽ xuất hiện sau khi có dữ liệu ván đấu được lưu."
            }
            action={normalizedQuery ? "Xóa tìm kiếm" : "Tìm đối thủ"}
            onAction={() => (normalizedQuery ? setQuery("") : go("rooms"))}
          />
        )}
      </section>
    </div>
  );
}

export function Profile() {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const {
    username,
    profileTone,
    go,
    openModal,
    viewRecord,
    signedIn,
    currentUser,
    playerStats,
    myMatches,
  } = useApp();
  const { avatar } = useExperience();
  const name = currentUser?.display_name ?? username;
  const totalGames = playerStats?.games_played ?? 0;
  const rating = playerStats?.elo ?? currentUser?.elo;
  const recent = currentUser ? myMatches.slice(0, 5) : [];
  return (
    <div className="page-stack profile-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">HÀNH TRÌNH CỦA RIÊNG BẠN</div>
          <Heading level={1}>Hồ sơ kỳ thủ</Heading>
          <div className="muted mt-xs">Thống kê tài khoản và kết quả được lưu trên máy chủ.</div>
        </div>
        <div className="inline profile-actions">
          <Button
            variant="neutral"
            iconStart={<Calendar size={16} />}
            onClick={() => (signedIn ? openModal("edit") : go("login"))}
          >
            {signedIn ? "Chỉnh sửa hồ sơ" : "Đăng nhập"}
          </Button>
        </div>
      </div>
      <section className="surface profile-hero">
        <div className="profile-hero-decoration" />
        <div className="profile-identity">
          <UserAvatar
            initials={playerInitials(name)}
            tone={profileTone}
            className="profile-large-avatar"
            elo={rating}
            current={signedIn}
          />
          <div>
            <div className="inline">
              <Heading level={1}>{signedIn ? name : "Kỳ hữu"}</Heading>
              {signedIn && <ShieldCheck size={20} className="verified-icon" />}
            </div>
            <div className="profile-level">
              <span className="level-dot" />
              {rating == null ? "Chưa xếp hạng" : <RankBadge elo={rating} />}
            </div>
            <div className="small muted profile-joined">
              <Calendar size={13} />
              {currentUser
                ? `Tham gia ${new Date(currentUser.created_at).toLocaleDateString(locale)}`
                : "Đăng nhập để xem thông tin tài khoản"}
            </div>
            <div className="tiny muted mt-xs">
              {avatar
                ? "Ảnh đại diện chỉ lưu trên trình duyệt này."
                : "Ảnh đại diện chưa được đồng bộ lên máy chủ."}
            </div>
          </div>
        </div>
        <div className="profile-hero-stats">
          <div>
            <span className="profile-stat-number">{rating?.toLocaleString(locale) ?? "—"}</span>
            <span className="muted">Điểm Elo</span>
          </div>
          <div>
            <span className="profile-stat-number">{signedIn ? totalGames : "—"}</span>
            <span className="muted">Tổng số trận</span>
          </div>
          <div>
            <span className="profile-stat-number">
              {playerStats?.rank ? String(playerStats.rank).padStart(2, "0") : "—"}
            </span>
            <span className="muted">Hạng cộng đồng</span>
          </div>
        </div>
      </section>
      {signedIn ? (
        <>
          <section className="surface profile-cultivation">
            <SectionTitle
              title="Hành trình tu luyện"
              action="Lộ trình 13 cảnh giới"
              onAction={() => openModal("ranks")}
            />
            {rating != null ? (
              <RankProgress elo={rating} />
            ) : (
              <div className="small muted">Chưa có điểm Elo để xác định cảnh giới.</div>
            )}
          </section>
          <div className="profile-content-grid">
            <section className="surface profile-performance">
              <SectionTitle title="Thành tích trên bàn cờ" />
              <div className="performance-content">
                <div className={`donut-chart ${totalGames ? "" : "donut-empty"}`}>
                  <div>
                    <strong>
                      {(playerStats?.win_rate ?? 0).toFixed(0)}
                      <span>%</span>
                    </strong>
                    <span>Tỷ lệ thắng</span>
                  </div>
                </div>
                <div className="performance-stats">
                  {[
                    { label: "Thắng", value: playerStats?.wins ?? 0, cls: "win" },
                    { label: "Hòa", value: playerStats?.draws ?? 0, cls: "draw" },
                    { label: "Thua", value: playerStats?.losses ?? 0, cls: "loss" },
                  ].map((stat) => (
                    <div className="performance-row" key={stat.cls}>
                      <span className={`performance-dot ${stat.cls}`} />
                      <span className="grow">{stat.label}</span>
                      <strong>{stat.value}</strong>
                      <span className="muted small">
                        {totalGames ? `${((stat.value / totalGames) * 100).toFixed(0)}%` : "0%"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </section>
            <section className="surface weekly-performance">
              <SectionTitle title="Đánh giá dữ liệu" />
              <div className="weekly-caption">
                <TrendingUp size={15} />
                {totalGames
                  ? `${totalGames} trận hoàn tất đã được tính vào thống kê.`
                  : "Chưa có trận hoàn tất được lưu."}
              </div>
            </section>
          </div>
          <section className="surface">
            <SectionTitle
              title="Những ván cờ gần đây"
              action="Xem toàn bộ lịch sử"
              onAction={() => go("history")}
            />
            {recent.length ? (
              <div className="profile-recent">
                {recent.map((match) => {
                  const opponent = opponentNameForUser(match, currentUser!.id);
                  const result = matchResultForUser(match, currentUser!.id);
                  const change = eloChangeForUser(match, currentUser!.id);
                  return (
                    <div className="profile-recent-row" key={match.match_key}>
                      <UserAvatar initials={playerInitials(opponent)} />
                      <div className="grow">
                        <div className="player-name">{opponent}</div>
                        <span className="small muted">{formatDate(match.finished_at, locale)}</span>
                      </div>
                      <span className={`result-tag ${result}`}>{resultLabels[result]}</span>
                      <span
                        className={`elo-change ${change > 0 ? "positive" : change < 0 ? "negative" : ""}`}
                      >
                        {change > 0 ? "+" : ""}
                        {change} Elo
                      </span>
                      <Button variant="neutral" size="small" onClick={() => viewRecord(match)}>
                        Xem lại <ArrowUpRight size={14} />
                      </Button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="Chưa có ván đấu được lưu"
                description="Kết quả thật sẽ xuất hiện sau khi hoàn tất trận trực tuyến."
                action="Tìm đối thủ"
                onAction={() => go("rooms")}
              />
            )}
          </section>
        </>
      ) : (
        <section className="surface">
          <EmptyState
            icon={<Target size={28} />}
            title="Đăng nhập để mở hồ sơ kỳ thủ"
            description="Thống kê Elo, lịch sử trận và thứ hạng lấy từ tài khoản của bạn."
            action="Đăng nhập"
            onAction={() => go("login")}
          />
        </section>
      )}
    </div>
  );
}
