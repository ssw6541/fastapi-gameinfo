import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmtNum, fmtPrice, type Genre, type GameSummary, type Status } from '../api'
import Carousel from '../components/Carousel'
import { CardSkeletons, EmptyState, ErrorState, GameCard } from '../components/common'
import {
  GameList2, PromoBanners, RankList, RecentPanel, ReleaseCalendar, ReviewFeed, SaleFeed, SectionHead,
  type Promo,
} from '../components/HomeSections'

type Tab = 'popular' | 'new' | 'sale' | 'upcoming'
const TABS: { id: Tab; label: string; en: string; title: string; desc: string; more: string }[] = [
  { id: 'popular', label: '인기', en: 'RANKING', title: '인기 게임', desc: '리뷰가 가장 많은 게임 순입니다.', more: '/search?sort=reviews' },
  { id: 'new', label: '신작', en: 'NEW', title: '요즘 뜨는 신작', desc: 'Steam에서 최근 출시되어 주목받는 게임입니다.', more: '/search?sort=newest' },
  { id: 'sale', label: '할인 중', en: 'SALE', title: '지금 할인 중', desc: '현재 할인 중인 게임이며, 리뷰가 많은 순입니다.', more: '/search?sort=reviews' },
  { id: 'upcoming', label: '출시 예정', en: 'SOON', title: '출시 예정작', desc: '곧 출시될 게임입니다. 평가와 리뷰는 출시 후에 쌓입니다.', more: '/search?sort=newest' },
]

const useList = (key: string, path: string, params: Record<string, string | number>) =>
  useQuery({ queryKey: ['portal', key], queryFn: ({ signal }) => api<GameSummary[]>(path, params, signal) })

export default function Home() {
  const [sp, setSp] = useSearchParams()
  const tabParam = sp.get('tab')
  const tab: Tab = TABS.some((x) => x.id === tabParam) ? (tabParam as Tab) : 'popular'
  const setTab = (t: Tab) => setSp(t === 'popular' ? {} : { tab: t }, { replace: true })
  const [genre, setGenre] = useState<number | null>(null)

  // menu links (/?tab=sale) should land on the browse section
  const browse = useRef<HTMLElement>(null)
  useEffect(() => { if (tabParam) browse.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [tabParam])

  const genres = useQuery({ queryKey: ['genres'], queryFn: ({ signal }) => api<Genre[]>('/genres', undefined, signal) })
  const status = useQuery({ queryKey: ['status'], queryFn: ({ signal }) => api<Status>('/status', undefined, signal) })
  const pop = useList('pop', '/games/featured', { limit: 24 })
  const news = useList('new', '/games/home', { tab: 'new', limit: 24 })
  const sale = useList('sale', '/games/home', { tab: 'sale', limit: 12 })
  const soon = useList('soon', '/games/home', { tab: 'upcoming', limit: 24 })

  const feat = useQuery({
    queryKey: ['home', tab, genre],
    queryFn: ({ signal }) =>
      tab === 'popular'
        ? api<GameSummary[]>('/games/featured', { genre, limit: 12 }, signal)
        : api<GameSummary[]>('/games/home', { tab, genre, limit: 12 }, signal),
  })
  const cur = TABS.find((x) => x.id === tab)!

  const promos: Promo[] = useMemo(() => {
    const out: Promo[] = []
    const p = pop.data?.[0], n = news.data?.[0], s = sale.data?.[0]
    if (p) out.push({ game: p, badge: 'HOT', line: `긍정 ${p.review_pct ?? '-'}% · 리뷰 ${fmtNum(p.review_count)}개` })
    if (n) out.push({ game: n, badge: 'NEW', line: `${n.release_date ?? '신규 출시'} 출시` })
    if (s) out.push({ game: s, badge: 'SALE', line: `-${s.price?.discount_percent ?? 0}% · ${fmtPrice(s.price, s.is_free)}` })
    return out
  }, [pop.data, news.data, sale.data])

  const calendar = useMemo(() => {
    const seen = new Set<number>()
    return [...(soon.data ?? []), ...(news.data ?? [])].filter((g) => !seen.has(g.appid) && seen.add(g.appid))
  }, [soon.data, news.data])

  return (
    <>
      <h1 className="sr-only">GameLens - Steam 게임 정보와 리뷰 검색</h1>

      <section className="promo-band" aria-label="추천 배너">
        <div className="container">
          {promos.length > 0
            ? <PromoBanners items={promos} />
            : <div className="promos skel-promos" aria-hidden><div /><div /><div /></div>}
        </div>
      </section>

      <div className="portal">
        <div className="portal-main">
          <section className="panel pick">
            <SectionHead en="PICK" title="오늘의 추천 게임" more="/search?sort=reviews" />
            <Carousel />
          </section>

          <ReviewFeed game={pop.data?.[0]} />
          <ReleaseCalendar games={calendar} />

          <section className="panel" ref={browse} id="browse">
            <SectionHead en={cur.en} title={cur.title} more={cur.more} moreLabel="전체 보기" />
            <div className="tabs" role="tablist" aria-label="게임 목록 종류">
              {TABS.map((x) => (
                <button key={x.id} role="tab" aria-selected={tab === x.id} className={`tab ${tab === x.id ? 'on' : ''}`} onClick={() => setTab(x.id)}>{x.label}</button>
              ))}
            </div>
            <div className="chips" role="group" aria-label="장르 필터">
              <button className={`chip ${genre === null ? 'on' : ''}`} onClick={() => setGenre(null)}>전체</button>
              {genres.data?.map((g) => (
                <button key={g.id} className={`chip ${genre === g.id ? 'on' : ''}`} onClick={() => setGenre(g.id)}>{g.name}</button>
              ))}
            </div>
            <p className="muted small tab-desc">{cur.desc}</p>
            {feat.isLoading && <CardSkeletons />}
            {feat.isError && <ErrorState error={feat.error} onRetry={() => feat.refetch()} />}
            {feat.data && feat.data.length === 0 && (
              <EmptyState title="표시할 게임이 없습니다" hint={tab === 'popular' ? '상단 검색창으로 게임을 검색하면 자동으로 목록이 채워집니다.' : '지금은 해당하는 게임이 없습니다. 잠시 후 다시 확인해 주세요.'} />
            )}
            {feat.data && feat.data.length > 0 && <div className="grid">{feat.data.map((g) => <GameCard key={g.appid} g={g} />)}</div>}
          </section>

          <GameList2 games={(pop.data ?? []).slice(5, 21)} />
        </div>

        <aside className="portal-side" aria-label="사이드 정보">
          <RecentPanel />
          <RankList en="TOP5" title="인기 게임 TOP5" games={pop.data ?? []} more="/search?sort=reviews"
            sub={(g) => `${g.genres.slice(0, 1).join('') || '게임'} · 긍정 ${g.review_pct ?? '-'}%`} />
          <RankList en="HOT" title="신작 TOP5" games={news.data ?? []} more="/?tab=new"
            sub={(g) => g.release_date ?? '신규 출시'} />
          <SaleFeed games={sale.data ?? []} />
          {status.data && (
            <p className="muted small side-note">
              수집된 게임 {fmtNum(status.data.catalog.games)}개 · 목록에 없는 게임도 검색하면 Steam에서 바로 찾아옵니다.{' '}
              <Link to="/search?sort=reviews">전체 보기</Link>
            </p>
          )}
        </aside>
      </div>
    </>
  )
}
