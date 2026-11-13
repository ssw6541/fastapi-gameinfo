import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, api, fmtDate, fmtNum, fmtPrice, type GameDetail } from '../api'
import { ErrorState, Spinner } from '../components/common'
import { ReviewsSection, StatsSection } from '../components/Reviews'

function Gallery({ shots, title }: { shots: string[]; title: string }) {
  const [i, setI] = useState(0)
  useEffect(() => { setI(0) }, [shots])
  if (shots.length === 0) return null
  return (
    <div className="gallery">
      <img className="shot-main" src={shots[i]} alt={`${title} 스크린샷 ${i + 1}`} />
      <div className="thumbs">
        {shots.map((s, k) => (
          <button key={s} className={k === i ? 'on' : ''} onClick={() => setI(k)} aria-label={`스크린샷 ${k + 1}`}>
            <img src={s} alt="" loading="lazy" />
          </button>
        ))}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children || (Array.isArray(children) && children.length === 0)) return null
  return <div className="irow"><dt>{label}</dt><dd>{children}</dd></div>
}

export default function Game() {
  const { appid: raw } = useParams()
  const appid = Number(raw)
  const valid = Number.isInteger(appid) && appid > 0
  const q = useQuery({
    queryKey: ['game', appid],
    queryFn: ({ signal }) => api<GameDetail>(`/games/${appid}`, undefined, signal),
    enabled: valid,
  })
  const [more, setMore] = useState(false)
  useEffect(() => { if (q.data) document.title = `${q.data.name} · GameLens` }, [q.data])

  if (!valid) return <ErrorState error={new ApiError(404, 'not_found', '올바르지 않은 AppID입니다.')} />
  if (q.isLoading) return <Spinner label="게임 정보를 불러오는 중…" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const g = q.data!
  const p = g.price
  const plats = Object.entries(g.platforms).filter(([, v]) => v).map(([k]) => ({ windows: 'Windows', mac: 'macOS', linux: 'Linux' }[k] ?? k))

  return (
    <article className="game">
      <nav className="crumbs"><Link to="/">홈</Link> / <span>{g.name}</span></nav>
      {g.stale && <p className="notice">Steam에서 최신 정보를 가져오지 못해 저장된 정보를 표시합니다.</p>}
      <section className="ghero">
        <img className="cover" src={g.header_image} alt={`${g.name} 대표 이미지`} />
        <div className="ginfo">
          <h1>{g.name}</h1>
          {g.name_en && g.name_en !== g.name && <div className="muted">{g.name_en}</div>}
          <p className="lead">{g.short_description || '설명 정보가 없습니다.'}</p>
          <div className="pricebox">
            {p && (p.discount_percent ?? 0) > 0 && <span className="disc">-{p.discount_percent}%</span>}
            {p && (p.discount_percent ?? 0) > 0 && p.initial != null && <s className="muted">₩{Math.round(p.initial).toLocaleString('ko-KR')}</s>}
            <strong className="bigprice">{g.coming_soon ? '출시 예정' : fmtPrice(p, g.is_free)}</strong>
            <a className="btn primary" href={g.store_url} target="_blank" rel="noopener noreferrer">Steam 상점 ↗</a>
            <a className="btn" href={`steam://store/${g.appid}`} title="Steam 앱이 설치되어 있으면 앱에서 바로 엽니다">Steam 앱에서 열기</a>
          </div>
          {g.genres.length > 0 && <div className="chips static">{g.genres.map((x) => <span className="chip" key={x}>{x}</span>)}</div>}
        </div>
      </section>

      <div className="gcols">
        <div className="gmain">
          <Gallery shots={g.screenshots} title={g.name ?? ''} />
          {g.movies.length > 0 && g.movies[0].url && (
            <video className="trailer" controls preload="none" poster={g.movies[0].thumbnail ?? undefined} src={g.movies[0].url} />
          )}
          {g.about && (
            <section>
              <h2>게임 소개</h2>
              <p className={`about ${more ? '' : 'clamp-about'}`}>{g.about}</p>
              {g.about.length > 500 && <button className="link" onClick={() => setMore(!more)}>{more ? '접기' : '더 보기'}</button>}
            </section>
          )}
        </div>
        <aside className="gside">
          <h2>상세 정보</h2>
          <dl>
            <Row label="AppID">{g.appid}</Row>
            <Row label="출시일">{g.release_date}</Row>
            <Row label="개발사">{g.developers.join(', ')}</Row>
            <Row label="배급사">{g.publishers.join(', ')}</Row>
            <Row label="플랫폼">{plats.join(' · ')}</Row>
            <Row label="카테고리">{g.categories.slice(0, 8).join(', ')}</Row>
            <Row label="지원 언어">{g.supported_languages}</Row>
            <Row label="메타크리틱">{g.metacritic}</Row>
            <Row label="Steam 추천 수">{g.recommendations ? fmtNum(g.recommendations) : null}</Row>
            <Row label="웹사이트">{g.website && /^https?:\/\//.test(g.website) ? <a href={g.website} target="_blank" rel="noopener noreferrer nofollow">{g.website}</a> : null}</Row>
          </dl>
          {g.fetched_at && <p className="muted small">정보 갱신: {fmtDate(g.fetched_at)}</p>}
        </aside>
      </div>

      <StatsSection appid={g.appid} summary={g.review_summary} />
      <ReviewsSection appid={g.appid} />
    </article>
  )
}
