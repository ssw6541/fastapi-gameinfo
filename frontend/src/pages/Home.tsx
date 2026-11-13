import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtNum, type Genre, type GameSummary, type Status } from '../api'
import Carousel from '../components/Carousel'
import SearchBox from '../components/SearchBox'
import { CardSkeletons, EmptyState, ErrorState, GameCard } from '../components/common'

type Tab = 'popular' | 'new' | 'sale' | 'upcoming'
const TABS: { id: Tab; label: string; en: string; title: string; desc: string; more: string }[] = [
  { id: 'popular', label: '인기', en: 'RANKING', title: '인기 게임', desc: '리뷰가 가장 많은 게임 순입니다.', more: '/search?sort=reviews' },
  { id: 'new', label: '신작', en: 'NEW', title: '요즘 뜨는 신작', desc: 'Steam에서 최근 출시되어 주목받는 게임입니다.', more: '/search?sort=newest' },
  { id: 'sale', label: '할인 중', en: 'SALE', title: '지금 할인 중', desc: '현재 할인 중인 게임이며, 리뷰가 많은 순입니다.', more: '/search?sort=reviews' },
  { id: 'upcoming', label: '출시 예정', en: 'SOON', title: '출시 예정작', desc: '곧 출시될 게임입니다. 평가와 리뷰는 출시 후에 쌓입니다.', more: '/search?sort=newest' },
]

export default function Home() {
  const [genre, setGenre] = useState<number | null>(null)
  const genres = useQuery({ queryKey: ['genres'], queryFn: ({ signal }) => api<Genre[]>('/genres', undefined, signal) })
  const status = useQuery({ queryKey: ['status'], queryFn: ({ signal }) => api<Status>('/status', undefined, signal) })
  const [tab, setTab] = useState<Tab>('popular')
  const feat = useQuery({
    queryKey: ['home', tab, genre],
    queryFn: ({ signal }) =>
      tab === 'popular'
        ? api<GameSummary[]>('/games/featured', { genre, limit: 12 }, signal)
        : api<GameSummary[]>('/games/home', { tab, limit: 12 }, signal),
  })
  const cur = TABS.find((x) => x.id === tab)!

  return (
    <>
      <section className="hero">
        <div className="coin px">★ INSERT COIN ★</div>
        <h1>Steam 게임, <span className="grad">한 번에 검색</span>하고 리뷰까지</h1>
        <p>영어·한국어 이름으로 게임을 찾고, 상세 정보와 실제 Steam 사용자 리뷰를 필터링해 보세요.</p>
        <SearchBox autoFocus />
        {status.data && (
          <p className="muted small hero-note">
            수집된 게임 {fmtNum(status.data.catalog.games)}개 · 목록에 없는 게임도 검색 시 Steam에서 바로 찾아옵니다.
          </p>
        )}
        <Carousel />
      </section>

      <section>
        <div className="section-head">
          <h2><span className="px">{cur.en}</span> {cur.title}</h2>
          <Link to={cur.more} className="muted">전체 보기 →</Link>
        </div>
        <div className="tabs" role="tablist" aria-label="게임 목록 종류">
          {TABS.map((x) => (
            <button key={x.id} role="tab" aria-selected={tab === x.id} className={`tab ${tab === x.id ? 'on' : ''}`} onClick={() => setTab(x.id)}>{x.label}</button>
          ))}
        </div>
        {tab === 'popular' && (
          <div className="chips" role="group" aria-label="장르 필터">
            <button className={`chip ${genre === null ? 'on' : ''}`} onClick={() => setGenre(null)}>전체</button>
            {genres.data?.map((g) => (
              <button key={g.id} className={`chip ${genre === g.id ? 'on' : ''}`} onClick={() => setGenre(g.id)}>{g.name}</button>
            ))}
          </div>
        )}
        <p className="muted small tab-desc">{cur.desc}</p>
        {feat.isLoading && <CardSkeletons />}
        {feat.isError && <ErrorState error={feat.error} onRetry={() => feat.refetch()} />}
        {feat.data && feat.data.length === 0 && (
          <EmptyState title="표시할 게임이 없습니다" hint={tab === 'popular' ? '상단 검색창으로 게임을 검색하면 자동으로 목록이 채워집니다.' : '지금은 해당하는 게임이 없습니다. 잠시 후 다시 확인해 주세요.'} />
        )}
        {feat.data && feat.data.length > 0 && <div className="grid">{feat.data.map((g) => <GameCard key={g.appid} g={g} />)}</div>}
      </section>
    </>
  )
}
