import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtNum, type Genre, type GameSummary, type Status } from '../api'
import SearchBox from '../components/SearchBox'
import { CardSkeletons, EmptyState, ErrorState, GameCard } from '../components/common'

export default function Home() {
  const [genre, setGenre] = useState<number | null>(null)
  const genres = useQuery({ queryKey: ['genres'], queryFn: ({ signal }) => api<Genre[]>('/genres', undefined, signal) })
  const status = useQuery({ queryKey: ['status'], queryFn: ({ signal }) => api<Status>('/status', undefined, signal) })
  const feat = useQuery({
    queryKey: ['featured', genre],
    queryFn: ({ signal }) => api<GameSummary[]>('/games/featured', { genre, limit: 12 }, signal),
  })

  return (
    <>
      <section className="hero">
        <h1>Steam 게임, <span className="grad">한 번에 검색</span>하고 리뷰까지</h1>
        <p>영어·한국어 이름으로 게임을 찾고, 상세 정보와 실제 Steam 사용자 리뷰를 필터링해 보세요.</p>
        <SearchBox autoFocus />
        {status.data && (
          <p className="muted small hero-note">
            수집된 게임 {fmtNum(status.data.catalog.games)}개 · 목록에 없는 게임도 검색 시 Steam에서 바로 찾아옵니다.
          </p>
        )}
      </section>

      <section>
        <div className="section-head">
          <h2>인기 게임</h2>
          <Link to="/search?sort=reviews" className="muted">전체 보기 →</Link>
        </div>
        <div className="chips" role="group" aria-label="장르 필터">
          <button className={`chip ${genre === null ? 'on' : ''}`} onClick={() => setGenre(null)}>전체</button>
          {genres.data?.map((g) => (
            <button key={g.id} className={`chip ${genre === g.id ? 'on' : ''}`} onClick={() => setGenre(g.id)}>{g.name}</button>
          ))}
        </div>
        {feat.isLoading && <CardSkeletons />}
        {feat.isError && <ErrorState error={feat.error} onRetry={() => feat.refetch()} />}
        {feat.data && feat.data.length === 0 && (
          <EmptyState title="아직 표시할 게임이 없습니다" hint="상단 검색창으로 게임을 검색하면 자동으로 목록이 채워집니다. (관리자: 수집 작업 실행 필요)" />
        )}
        {feat.data && feat.data.length > 0 && <div className="grid">{feat.data.map((g) => <GameCard key={g.appid} g={g} />)}</div>}
      </section>
    </>
  )
}
