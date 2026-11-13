import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api, fmtDate, fmtHours, fmtNum, fmtPrice, type GameSummary, type ReviewsResponse,
} from '../api'
import { imgFallback } from './common'

const bigArt = (appid: number) => `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/capsule_616x353.jpg`
const imgChain = (g: GameSummary) => (e: React.SyntheticEvent<HTMLImageElement>) => imgFallback(e.currentTarget, g.header_image, g.capsule_image)

export function SectionHead({ en, title, more, moreLabel = '더보기' }: { en: string; title: string; more?: string; moreLabel?: string }) {
  return (
    <div className="ps-head">
      <h2><span className="px">{en}</span> {title}</h2>
      {more && <Link to={more} className="more">{moreLabel} ›</Link>}
    </div>
  )
}

/* ------------------------------------------------------------ promo banners (top band) */
export interface Promo { game: GameSummary; badge: 'HOT' | 'NEW' | 'SALE'; line: string }

export function PromoBanners({ items }: { items: Promo[] }) {
  return (
    <div className="promos">
      {items.map(({ game: g, badge, line }) => (
        <Link key={badge + g.appid} to={`/game/${g.appid}`} className="promo">
          <img src={bigArt(g.appid)} alt="" onError={imgChain(g)} />
          <div className="promo-shade" aria-hidden />
          <span className={`px badge b-${badge.toLowerCase()}`}>{badge}</span>
          <div className="promo-txt">
            <strong>{g.name}</strong>
            <span>{line}</span>
          </div>
        </Link>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------ ranked list (sidebar) */
export function RankList({ en, title, games, more, sub }: { en: string; title: string; games: GameSummary[]; more?: string; sub: (g: GameSummary) => string }) {
  return (
    <section className="panel">
      <SectionHead en={en} title={title} more={more} />
      <ol className="ranklist">
        {games.slice(0, 5).map((g, i) => (
          <li key={g.appid}>
            <Link to={`/game/${g.appid}`}>
              <span className={`rank r${i + 1}`}>{i + 1}</span>
              <img src={g.capsule_image} alt="" loading="lazy" onError={imgChain(g)} />
              <span className="rk-main"><strong>{g.name}</strong><small>{sub(g)}</small></span>
            </Link>
          </li>
        ))}
        {games.length === 0 && <li className="muted small pad">표시할 게임이 없습니다.</li>}
      </ol>
    </section>
  )
}

/* ------------------------------------------------------------ sale feed (sidebar, "이벤트 소식" analogue) */
export function SaleFeed({ games }: { games: GameSummary[] }) {
  return (
    <section className="panel">
      <SectionHead en="SALE" title="특가 소식" more="/?tab=sale" />
      <ul className="salefeed">
        {games.slice(0, 4).map((g) => (
          <li key={g.appid}>
            <Link to={`/game/${g.appid}`}>
              <img src={g.header_image} alt="" loading="lazy" onError={imgChain(g)} />
              <span className="sf-main">
                <strong>{g.name}</strong>
                <span><span className="disc">-{g.price?.discount_percent ?? 0}%</span> <b className="price">{fmtPrice(g.price, g.is_free)}</b></span>
              </span>
            </Link>
          </li>
        ))}
        {games.length === 0 && <li className="muted small pad">현재 할인 정보가 없습니다.</li>}
      </ul>
    </section>
  )
}

/* ------------------------------------------------------------ recently viewed (localStorage) */
interface Recent { appid: number; name: string; img: string }
const RKEY = 'gl_recent'
const readRecent = (): Recent[] => {
  try { return JSON.parse(localStorage.getItem(RKEY) ?? '[]') as Recent[] } catch { return [] }
}
export function rememberGame(g: Recent) {
  try {
    const next = [g, ...readRecent().filter((x) => x.appid !== g.appid)].slice(0, 6)
    localStorage.setItem(RKEY, JSON.stringify(next))
  } catch { /* storage unavailable (private mode) */ }
}
export function RecentPanel() {
  const [items, setItems] = useState<Recent[]>([])
  useEffect(() => { setItems(readRecent()) }, [])
  return (
    <section className="panel">
      <SectionHead en="RECENT" title="최근 본 게임" />
      {items.length === 0
        ? <p className="muted small pad">아직 본 게임이 없습니다. 게임 상세 페이지를 열면 여기에 기록돼요.</p>
        : (
          <ul className="recent">
            {items.map((g) => (
              <li key={g.appid}>
                <Link to={`/game/${g.appid}`}><img src={g.img} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} /><span>{g.name}</span></Link>
              </li>
            ))}
          </ul>
        )}
      {items.length > 0 && <button className="link small" onClick={() => { try { localStorage.removeItem(RKEY) } catch { /* ignore */ } setItems([]) }}>기록 지우기</button>}
    </section>
  )
}

/* ------------------------------------------------------------ review feed ("라운지 인기글" analogue) */
export function ReviewFeed({ game }: { game: GameSummary | undefined }) {
  const q = useQuery({
    queryKey: ['feed-reviews', game?.appid],
    queryFn: ({ signal }) => api<ReviewsResponse>(`/games/${game!.appid}/reviews`, { sort: 'helpful', language: 'koreana', per_page: 6, day_range: 365 }, signal),
    enabled: !!game,
  })
  const rows = (q.data?.reviews ?? []).filter((r) => r.text.trim().length > 20).slice(0, 5)
  return (
    <section className="panel">
      <SectionHead en="REVIEW" title={game ? `${game.name} 인기 리뷰` : '인기 리뷰'} more={game ? `/game/${game.appid}#reviews` : undefined} />
      {q.isLoading && <p className="muted small pad">리뷰를 불러오는 중…</p>}
      {q.isError && <p className="muted small pad">리뷰를 불러오지 못했습니다.</p>}
      {q.data && rows.length === 0 && <p className="muted small pad">표시할 한국어 리뷰가 없습니다.</p>}
      <ul className="feed">
        {rows.map((r) => (
          <li key={r.id}>
            <Link to={`/game/${game!.appid}#reviews`}>
              <span className={`verdict ${r.voted_up ? 'up' : 'down'}`}>{r.voted_up ? '👍' : '👎'}</span>
              <span className="fd-main">
                <span className="fd-text">{r.text}</span>
                <small className="muted">플레이 {fmtHours(r.playtime_forever_min)} · 도움 {fmtNum(r.votes_up)} · {fmtDate(r.created_at)}</small>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/* ------------------------------------------------------------ release calendar ("이번 달 출시 게임" analogue) */
const dayKey = (d: Date, utc = false) => utc ? `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}` : `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`

export function ReleaseCalendar({ games }: { games: GameSummary[] }) {
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d }), [])
  const byDay = useMemo(() => {
    const m = new Map<string, GameSummary[]>()
    for (const g of games) {
      if (!g.release_ts) continue
      const k = dayKey(new Date(g.release_ts * 1000), true)
      m.set(k, [...(m.get(k) ?? []), g])
    }
    return m
  }, [games])
  const firstWithData = days.findIndex((d) => byDay.has(dayKey(d)))
  const [sel, setSel] = useState<number | null>(null)
  const cur = sel ?? (firstWithData >= 0 ? firstWithData : 0)
  const list = (byDay.get(dayKey(days[cur])) ?? []).slice(0, 8)
  const today = Date.now()
  return (
    <section className="panel">
      <SectionHead en="CALENDAR" title="이번 주 출시 게임" more="/?tab=upcoming" />
      <div className="daytabs" role="tablist" aria-label="출시 날짜">
        {days.map((d, i) => (
          <button key={i} role="tab" aria-selected={cur === i} className={`daytab ${cur === i ? 'on' : ''}`} onClick={() => setSel(i)}>
            <small>{d.toLocaleDateString('ko-KR', { weekday: 'short' })}</small>
            {String(d.getMonth() + 1).padStart(2, '0')}.{String(d.getDate()).padStart(2, '0')}
            {byDay.has(dayKey(d)) && <i className="dot" aria-hidden />}
          </button>
        ))}
      </div>
      {list.length === 0
        ? <p className="muted small pad">이 날짜에 확인된 출시작이 없습니다. 다른 날짜를 선택해 보세요.</p>
        : (
          <div className="relgrid">
            {list.map((g) => (
              <Link key={g.appid} to={`/game/${g.appid}`} className="rel">
                <span className="rel-img">
                  <img src={g.header_image} alt="" loading="lazy" onError={imgChain(g)} />
                  <span className={`px badge ${(g.release_ts ?? 0) * 1000 > today ? 'b-soon' : 'b-new'}`}>{(g.release_ts ?? 0) * 1000 > today ? '출시예정' : '출시'}</span>
                </span>
                <strong>{g.name}</strong>
                <small className="muted">{g.genres.slice(0, 2).join(' · ') || g.release_date}</small>
              </Link>
            ))}
          </div>
        )}
    </section>
  )
}

/* ------------------------------------------------------------ two-column game list ("공식 게임 라운지") */
export function GameList2({ games }: { games: GameSummary[] }) {
  return (
    <section className="panel">
      <SectionHead en="GAMES" title="인기 게임 더 보기" more="/search?sort=reviews" />
      <ul className="list2">
        {games.map((g) => (
          <li key={g.appid}>
            <Link to={`/game/${g.appid}`}>
              <img src={g.capsule_image} alt="" loading="lazy" onError={imgChain(g)} />
              <span><strong>{g.name}</strong><small className="muted">{g.genres.slice(0, 2).join(' · ') || (g.review_pct != null ? `긍정 ${g.review_pct}%` : '')}</small></span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
