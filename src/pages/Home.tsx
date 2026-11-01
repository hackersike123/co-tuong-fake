import { Button } from "@figma/astraui";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Calendar,
  ChevronRight,
  Clock,
  Crown,
  Flag,
  Lightbulb,
  Plus,
  Sprout,
  Swords,
  Target,
  TrendingUp,
  Trophy,
  Users,
} from "lucide-react";
import {
  ChessBoard,
  Heading,
  OnlineStatus,
  RoomCard,
  SectionTitle,
  UserAvatar,
} from "../components";
import { useApp } from "../context";
import { intlLocale } from "../i18n-core";
import { useLanguage } from "../i18n";
import {
  eloChangeForUser,
  matchResultForUser,
  opponentNameForUser,
  playerInitials,
  resultLabels,
} from "../data";
import { RankBadge, RankProgress } from "../rank-ui";
import { ArenaAtmosphere } from "../experience/effects";

export default function Home() {
  const { language } = useLanguage();
  const locale = intlLocale(language);
  const {
    go,
    username,
    signedIn,
    currentUser,
    playerStats,
    leaderboard,
    myMatches,
    communitySummary,
    profileTone,
    openModal,
    roomList,
    viewRecord,
  } = useApp();
  const topPlayers = leaderboard.slice(0, 4);
  const today = new Intl.DateTimeFormat(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
  const weeklyChange = myMatches
    .filter((match) => {
      const age = Date.now() - new Date(match.finished_at).getTime();
      return age >= 0 && age <= 7 * 24 * 60 * 60 * 1000;
    })
    .reduce((sum, match) => sum + (currentUser ? eloChangeForUser(match, currentUser.id) : 0), 0);
  const rating = playerStats?.elo ?? currentUser?.elo;
  return (
    <div className="home-page page-stack">
      <ArenaAtmosphere />
      <div className="welcome-row">
        <div>
          <Heading level={1}>
            Xin chào, {signedIn ? username : "kỳ hữu"}
            <span className="welcome-dot">.</span>
          </Heading>
          <div className="muted welcome-subtitle">
            Một ván cờ hay đang chờ bạn. Sẵn sàng khai cuộc?
          </div>
        </div>
        <div className="today-label">
          <Calendar size={15} />
          {today}
        </div>
      </div>
      <div className="dashboard-grid">
        <div className="dashboard-main">
          <section className="hero-card">
            <div className="hero-content">
              <div className="eyebrow">
                <span className="eyebrow-line" />
                TÂM TĨNH · TRÍ SÁNG
              </div>
              <Heading level={2} className="hero-title">
                Khai cuộc hôm nay,
                <br />
                bứt phá từng nước đi.
              </Heading>
              <div className="hero-description">
                Tìm một đối thủ xứng tầm, hay đơn giản
                <br className="desktop-break" /> là tận hưởng một ván cờ thật hay.
              </div>
              <div className="hero-actions">
                <Button iconEnd={<ArrowRight size={16} />} onClick={() => go("rooms")}>
                  Chơi ngay
                </Button>
                <Button variant="neutral" iconStart={<Bot size={17} />} onClick={() => go("ai")}>
                  Chơi với máy
                </Button>
              </div>
              <div className="hero-community">
                <div className="mini-avatar-stack">
                  {topPlayers.slice(0, 3).map((player) => (
                    <UserAvatar
                      key={player.user_id}
                      initials={playerInitials(player.display_name)}
                      tone="sage"
                      size="small"
                      elo={player.elo}
                      current={player.user_id === currentUser?.id}
                    />
                  ))}
                </div>
                <span>
                  {communitySummary
                    ? `${communitySummary.registered_players} kỳ thủ · ${communitySummary.open_public_rooms} phòng đang mở`
                    : "Số liệu cộng đồng đang tải từ máy chủ"}
                </span>
              </div>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="hero-orbit orbit-one" />
              <div className="hero-orbit orbit-two" />
              <div className="hero-board">
                <ChessBoard small />
              </div>
              <div className="hero-stamp">
                KỲ
                <br />
                TIÊN
                <br />
                HỘI
              </div>
              <div className="hero-art-caption">
                <span className="caption-line" />
                Mỗi nước cờ, một tầm nhìn.
              </div>
            </div>
          </section>
          <div className="quick-action-grid">
            <Button variant="neutral" className="quick-action" onClick={() => openModal("create")}>
              <span className="quick-icon tone-rose">
                <Plus size={22} strokeWidth={1.7} />
              </span>
              <span className="quick-copy">
                <span className="quick-title">Tạo phòng</span>
                <span className="small muted">Mời bạn bè giao lưu</span>
              </span>
              <ChevronRight size={17} className="muted" />
            </Button>
            <Button variant="neutral" className="quick-action" onClick={() => go("rooms")}>
              <span className="quick-icon tone-sage">
                <Swords size={22} strokeWidth={1.7} />
              </span>
              <span className="quick-copy">
                <span className="quick-title">Tìm đối thủ</span>
                <span className="small muted">Phòng công khai đang hoạt động</span>
              </span>
              <ChevronRight size={17} className="muted" />
            </Button>
            <Button variant="neutral" className="quick-action" onClick={() => openModal("rules")}>
              <span className="quick-icon tone-sand">
                <Sprout size={22} strokeWidth={1.7} />
              </span>
              <span className="quick-copy">
                <span className="quick-title">Luật cờ tướng</span>
                <span className="small muted">Cách đi quân và luật cơ bản</span>
              </span>
              <ChevronRight size={17} className="muted" />
            </Button>
          </div>
          <section className="surface lobby-preview">
            <SectionTitle
              title="Sảnh đấu đang mở"
              subtitle="Phòng công khai đang chờ đối thủ."
              action="Xem tất cả"
              onAction={() => go("rooms")}
            />
            <div className="home-room-grid">
              {roomList.slice(0, 3).map((room) => (
                <RoomCard key={room.id} room={room} compact />
              ))}
            </div>
            <div className="lobby-preview-footer">
              <OnlineStatus>{roomList.length} phòng đang chờ</OnlineStatus>
              <span className="small muted">
                <span className="live-pulse" />
                WebSocket trực tiếp
              </span>
            </div>
          </section>
          <section className="surface recent-section">
            <SectionTitle
              title="Ván đấu gần đây"
              action="Xem lịch sử"
              onAction={() => go("history")}
            />
            {signedIn && currentUser && myMatches.length ? (
              <div className="table-wrap">
                <table className="data-table recent-table">
                  <thead>
                    <tr>
                      <th>Đối thủ</th>
                      <th>Kết quả</th>
                      <th>Thay đổi Elo</th>
                      <th>Thời gian</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {myMatches.slice(0, 3).map((match) => {
                      const opponent = opponentNameForUser(match, currentUser.id);
                      const result = matchResultForUser(match, currentUser.id);
                      const change = eloChangeForUser(match, currentUser.id);
                      return (
                        <tr key={match.match_key}>
                          <td>
                            <div className="inline">
                              <UserAvatar initials={playerInitials(opponent)} size="medium" />
                              <div>
                                <div className="player-name">{opponent}</div>
                                <div className="small muted">{match.room_name}</div>
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
                              {change} <span className="small">Elo</span>
                            </span>
                          </td>
                          <td className="muted small">
                            {new Date(match.finished_at).toLocaleString(locale)}
                          </td>
                          <td>
                            <Button
                              variant="subtle"
                              size="small"
                              onClick={() => viewRecord(match)}
                              aria-label={`Xem lại ván với ${opponent}`}
                              className="table-arrow"
                            >
                              <ArrowUpRight size={17} />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : signedIn ? (
              <div className="guest-history">
                <Clock size={24} />
                <div>
                  <Heading level={3}>Chưa có ván đấu được lưu</Heading>
                  <div className="muted small">
                    Kết quả trận trực tuyến giữa hai tài khoản sẽ xuất hiện tại đây.
                  </div>
                </div>
                <Button variant="neutral" onClick={() => go("rooms")}>
                  Tìm đối thủ
                </Button>
              </div>
            ) : (
              <div className="guest-history">
                <Clock size={24} />
                <div>
                  <Heading level={3}>Lưu lại hành trình kỳ thủ của bạn</Heading>
                  <div className="muted small">
                    Đăng nhập để xem lịch sử và theo dõi sự tiến bộ.
                  </div>
                </div>
                <Button variant="neutral" onClick={() => go("login")}>
                  Đăng nhập
                </Button>
              </div>
            )}
          </section>
        </div>
        <aside className="dashboard-aside">
          <section className="surface profile-summary">
            <div className="between">
              <span className="aside-label">PHONG ĐỘ CỦA BẠN</span>
              <Target size={17} className="muted" />
            </div>
            <div className="summary-profile">
              <UserAvatar
                initials={signedIn ? playerInitials(username) : "KH"}
                tone={profileTone}
                className="summary-avatar"
                current={signedIn}
              />
              <div>
                <Heading level={3}>{signedIn ? username : "Kỳ hữu mới"}</Heading>
                <div className="profile-level">
                  <span className="level-dot" />
                  {signedIn && rating != null ? (
                    <RankBadge elo={rating} compact />
                  ) : (
                    "Sẵn sàng khai cuộc"
                  )}
                </div>
              </div>
              <Button
                variant="subtle"
                size="small"
                onClick={() => go(signedIn ? "profile" : "login")}
                aria-label="Xem hồ sơ"
                className="table-arrow"
              >
                <ArrowUpRight size={17} />
              </Button>
            </div>
            <div className="elo-summary">
              <div>
                <span className="elo-large">
                  {signedIn && rating != null ? rating.toLocaleString(locale) : "—"}
                </span>
                <span className="elo-label">Elo</span>
              </div>
              <span className="trend-label">
                <TrendingUp size={14} />
                {weeklyChange > 0 ? "+" : ""}
                {weeklyChange} <span>tuần này</span>
              </span>
            </div>
            {signedIn && rating != null ? (
              <RankProgress elo={rating} />
            ) : (
              <div className="small muted">Đăng nhập để xem cảnh giới và điểm Elo.</div>
            )}
            <Button
              variant="subtle"
              size="small"
              className="rank-roadmap-link"
              iconEnd={<ArrowRight size={13} />}
              onClick={() => openModal("ranks")}
            >
              Lộ trình 13 cảnh giới
            </Button>
            <div className="summary-stats">
              <div>
                <span className="stat-icon tone-blue">
                  <Flag size={17} />
                </span>
                <div className="summary-stat-value">
                  {signedIn ? (playerStats?.games_played ?? 0) : "0"}
                </div>
                <span className="small muted">Trận đã chơi</span>
              </div>
              <div>
                <span className="stat-icon tone-sage">
                  <Trophy size={17} />
                </span>
                <div className="summary-stat-value">
                  {signedIn ? (playerStats?.win_rate ?? 0).toFixed(0) : "0"}
                  <span>%</span>
                </div>
                <span className="small muted">Tỷ lệ thắng</span>
              </div>
            </div>
            {!signedIn && (
              <Button onClick={() => go("register")} className="button-full">
                Tạo tài khoản miễn phí
              </Button>
            )}
          </section>
          <section className="surface top-players">
            <SectionTitle
              title="Cao thủ tuần này"
              onAction={() => go("leaderboard")}
              action="Xem thêm"
            />
            <div className="rank-list">
              {topPlayers.map((player, i) => (
                <Button
                  key={player.user_id}
                  variant="subtle"
                  className="rank-row"
                  onClick={() => go("leaderboard")}
                >
                  <span className={`rank-position position-${i}`}>
                    {i === 0 ? <Crown size={18} /> : String(i + 1).padStart(2, "0")}
                  </span>
                  <UserAvatar
                    initials={playerInitials(player.display_name)}
                    tone="sage"
                    size="medium"
                    elo={player.elo}
                    current={player.user_id === currentUser?.id}
                  />
                  <span className="rank-player">
                    <span>{player.display_name}</span>
                    <RankBadge elo={player.elo} compact />
                  </span>
                  <span className="rank-elo">
                    {player.elo.toLocaleString(locale)}
                    <span>Elo</span>
                  </span>
                </Button>
              ))}
              {!topPlayers.length && (
                <div className="guest-history muted small">
                  Chưa có người chơi đủ dữ liệu để xếp hạng.
                </div>
              )}
            </div>
            <div className="ranking-update">
              <Clock size={12} />
              {communitySummary
                ? `${communitySummary.registered_players} tài khoản đã đăng ký`
                : "Đang chờ dữ liệu máy chủ"}
            </div>
          </section>
          <section className="wisdom-card">
            <div className="wisdom-label">
              <Lightbulb size={17} strokeWidth={1.5} />
              GÓC KỲ THỦ
            </div>
            <Heading level={2}>
              Chậm một nước,
              <br />
              sáng cả bàn cờ.
            </Heading>
            <div className="wisdom-description">
              Đừng vội ăn quân. Hãy nhìn thế cờ trước khi nhìn lợi thế.
            </div>
            <Button
              variant="subtle"
              iconEnd={<ArrowRight size={16} />}
              onClick={() => openModal("tips")}
            >
              Khám phá mẹo chơi
            </Button>
            <span className="wisdom-deco" aria-hidden="true">
              <Crown size={110} strokeWidth={1} />
            </span>
          </section>
          <div className="fair-play">
            <span className="fair-play-icon">
              <Users size={17} />
            </span>
            <div>
              <span>Văn minh trên từng nước cờ</span>
              <div className="muted small">Tôn trọng đối thủ. Tận hưởng cuộc chơi.</div>
            </div>
          </div>
        </aside>
      </div>
      <footer className="page-footer">
        <span>© 2026 Kỳ Tiên Hội. Kết nối đam mê cờ tướng.</span>
        <span>Kết quả, Elo và thứ hạng lấy từ các ván đã lưu.</span>
      </footer>
    </div>
  );
}
