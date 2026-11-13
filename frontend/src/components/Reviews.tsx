import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  api, fmtDate, fmtHours, fmtNum, LANGUAGES, type Review, type ReviewsResponse, type ReviewStats, type ReviewSummary,
} from '../api'
import { ErrorState, Spinner } from './common'

const POS = '#4ade80'
const NEG = '#f87171'
const langName = (l: string) => LANGUAGES[l] ?? l

/* ------------------------------------------------------------------ review card */
function ReviewCard({ r }: { r: Review }) {
  const [open, setOpen] = useState(false)
  const long = r.text.length > 600
  return (
    <article className={`review ${r.voted_up ? 'up' : 'down'}`}>
      <header>
        <span className={`verdict ${r.voted_up ? 'up' : 'down'}`}>{r.voted_up ? '👍 추천' : '👎 비추천'}</span>
        <span className="muted small">
          플레이 {fmtHours(r.playtime_forever_min)}
          {r.playtime_at_review_min > 0 && r.playtime_at_review_min !== r.playtime_forever_min && ` (작성 시 ${fmtHours(r.playtime_at_review_min)})`}
        </span>
        <span className="muted small">{fmtDate(r.created_at)}</span>
        <span className="muted small lang">{r.language ? langName(r.language) : ''}</span>
      </header>
      <p className={`rtext ${long && !open ? 'clamp' : ''}`}>{r.text || '(내용 없음)'}</p>
      {long && <button className="link" onClick={() => setOpen(!open)}>{open ? '접기' : '더 보기'}</button>}
      <footer className="muted small">
        <span>👍 도움이 돼요 {fmtNum(r.votes_up)}</span>
        {r.votes_funny > 0 && <span>😄 재밌어요 {fmtNum(r.votes_funny)}</span>}
        {r.early_access && <span className="tag">앞서 해보기 중 작성</span>}
        {r.received_for_free && <span className="tag">무료로 받음</span>}
        {!r.steam_purchase && <span className="tag">Steam 외 구매</span>}
        {r.url && <a href={r.url} target="_blank" rel="noopener noreferrer">Steam에서 보기 ↗</a>}
      </footer>
    </article>
  )
}

/* ------------------------------------------------------------------ summary bar */
export function SummaryBar({ s }: { s: ReviewSummary }) {
  const pct = s.positive_ratio != null ? Math.round(s.positive_ratio * 1000) / 10 : null
  return (
    <div className="sumbar">
      <div className="sumhead">
        <strong>{s.score_desc ? scoreKo(s.score_desc) : '평가'}</strong>
        <span>{pct != null ? `${pct}% 긍정` : ''}</span>
        <span className="muted">Steam 전체 리뷰 {fmtNum(s.total_reviews)}개 (긍정 {fmtNum(s.total_positive)} · 부정 {fmtNum(s.total_negative)})</span>
      </div>
      <div className="bar" role="img" aria-label={`긍정 ${pct}%`}>
        <span style={{ width: `${pct ?? 0}%`, background: POS }} />
        <span style={{ width: `${pct != null ? 100 - pct : 0}%`, background: NEG }} />
      </div>
    </div>
  )
}

const SCORE_KO: Record<string, string> = {
  'Overwhelmingly Positive': '압도적으로 긍정적', 'Very Positive': '매우 긍정적', Positive: '긍정적',
  'Mostly Positive': '대체로 긍정적', Mixed: '복합적', 'Mostly Negative': '대체로 부정적', Negative: '부정적',
  'Very Negative': '매우 부정적', 'Overwhelmingly Negative': '압도적으로 부정적',
}
const scoreKo = (s: string) => SCORE_KO[s] ?? s

/* ------------------------------------------------------------------ filters */
interface Filters { sort: string; language: string; review_type: string; purchase_type: string; day_range: string }
const DEFAULT: Filters = { sort: 'helpful', language: 'koreana', review_type: 'all', purchase_type: 'all', day_range: '' }

function FilterBar({ f, set, mode, setMode }: { f: Filters; set: (p: Partial<Filters>) => void; mode: 'pages' | 'more'; setMode: (m: 'pages' | 'more') => void }) {
  return (
    <div className="rfilters">
      <label>정렬
        <select value={f.sort} onChange={(e) => set({ sort: e.target.value })}>
          <option value="helpful">유용성순</option><option value="recent">최신순</option><option value="updated">최근 수정순</option>
        </select>
      </label>
      <label>언어
        <select value={f.language} onChange={(e) => set({ language: e.target.value })}>
          {Object.entries(LANGUAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>평가
        <select value={f.review_type} onChange={(e) => set({ review_type: e.target.value })}>
          <option value="all">전체</option><option value="positive">추천만</option><option value="negative">비추천만</option>
        </select>
      </label>
      <label>구매
        <select value={f.purchase_type} onChange={(e) => set({ purchase_type: e.target.value })}>
          <option value="all">전체</option><option value="steam">Steam 구매</option><option value="non_steam_purchase">Steam 외 구매</option>
        </select>
      </label>
      {f.sort === 'helpful' && (
        <label>기간
          <select value={f.day_range} onChange={(e) => set({ day_range: e.target.value })}>
            <option value="">전체 기간</option><option value="30">최근 30일</option><option value="90">최근 90일</option><option value="365">최근 1년</option>
          </select>
        </label>
      )}
      <label>보기 방식
        <select value={mode} onChange={(e) => setMode(e.target.value as 'pages' | 'more')}>
          <option value="pages">페이지 넘기기</option><option value="more">이어서 더 보기</option>
        </select>
      </label>
    </div>
  )
}

const toParams = (f: Filters, extra: Record<string, string | number>) => ({
  sort: f.sort, language: f.language, review_type: f.review_type, purchase_type: f.purchase_type,
  day_range: f.sort === 'helpful' ? f.day_range : '', per_page: 20, ...extra,
})

/* ------------------------------------------------------------------ paged list (cursor stack) */
function PagedList({ appid, f }: { appid: number; f: Filters }) {
  const [stack, setStack] = useState<string[]>(['*']) // cursors of pages 1..n
  const [idx, setIdx] = useState(0)
  const key = JSON.stringify(f)
  const [seenKey, setSeenKey] = useState(key)
  if (seenKey !== key) { setSeenKey(key); setStack(['*']); setIdx(0) } // filters changed -> back to page 1

  const q = useQuery({
    queryKey: ['reviews', appid, f, stack[idx]],
    queryFn: ({ signal }) => api<ReviewsResponse>(`/games/${appid}/reviews`, toParams(f, { cursor: stack[idx] }), signal),
    placeholderData: keepPreviousData,
  })
  const next = () => {
    if (!q.data?.cursor) return
    setStack((s) => (s[idx + 1] === q.data!.cursor ? s : [...s.slice(0, idx + 1), q.data!.cursor!]))
    setIdx(idx + 1)
  }
  if (q.isLoading) return <Spinner label="리뷰를 불러오는 중…" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data!
  return (
    <>
      {d.reviews.length === 0 ? <p className="state">조건에 맞는 리뷰가 없습니다. 언어나 평가 필터를 바꿔 보세요.</p> : (
        <div className={`rlist ${q.isPlaceholderData ? 'dim' : ''}`}>{d.reviews.map((r) => <ReviewCard key={r.id} r={r} />)}</div>
      )}
      <nav className="pager" aria-label="리뷰 페이지">
        <button className="btn" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>← 이전</button>
        <span>{idx + 1} 페이지</span>
        <button className="btn" disabled={!d.has_more} onClick={next}>다음 →</button>
      </nav>
    </>
  )
}

/* ------------------------------------------------------------------ infinite list (append, dedupe) */
function MoreList({ appid, f }: { appid: number; f: Filters }) {
  const q = useInfiniteQuery({
    queryKey: ['reviews-inf', appid, f],
    initialPageParam: '*',
    queryFn: ({ pageParam, signal }) => api<ReviewsResponse>(`/games/${appid}/reviews`, toParams(f, { cursor: pageParam }), signal),
    getNextPageParam: (last) => (last.has_more ? last.cursor : undefined),
  })
  const reviews = useMemo(() => {
    const seen = new Set<string>()
    return (q.data?.pages ?? []).flatMap((p) => p.reviews).filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)))
  }, [q.data])
  if (q.isLoading) return <Spinner label="리뷰를 불러오는 중…" />
  if (q.isError && reviews.length === 0) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return (
    <>
      {reviews.length === 0 ? <p className="state">조건에 맞는 리뷰가 없습니다. 언어나 평가 필터를 바꿔 보세요.</p> : (
        <div className="rlist">{reviews.map((r) => <ReviewCard key={r.id} r={r} />)}</div>
      )}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.fetchNextPage()} />}
      <div className="pager">
        {q.hasNextPage
          ? <button className="btn" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>{q.isFetchingNextPage ? '불러오는 중…' : `리뷰 더 불러오기 (${reviews.length}개 표시 중)`}</button>
          : reviews.length > 0 && <span className="muted">모든 리뷰를 불러왔습니다 ({reviews.length}개)</span>}
      </div>
    </>
  )
}

export function ReviewsSection({ appid }: { appid: number }) {
  const [f, setF] = useState<Filters>(DEFAULT)
  const [mode, setMode] = useState<'pages' | 'more'>('pages')
  return (
    <section id="reviews" aria-labelledby="rev-h">
      <h2 id="rev-h">사용자 리뷰</h2>
      <FilterBar f={f} set={(p) => setF({ ...f, ...p })} mode={mode} setMode={setMode} />
      <p className="muted small">언어·평가 필터는 목록에만 적용되며, 위 Steam 전체 집계 수치는 필터와 무관합니다.</p>
      {mode === 'pages' ? <PagedList appid={appid} f={f} /> : <MoreList appid={appid} f={f} />}
    </section>
  )
}

/* ------------------------------------------------------------------ stats / charts */
export function StatsSection({ appid, summary }: { appid: number; summary: ReviewSummary | null }) {
  const [lang, setLang] = useState('all')
  const q = useQuery({
    queryKey: ['stats', appid, lang],
    queryFn: ({ signal }) => api<ReviewStats>(`/games/${appid}/review-stats`, { pages: 3, language: lang }, signal),
  })
  return (
    <section aria-labelledby="stat-h">
      <div className="section-head">
        <h2 id="stat-h">리뷰 통계</h2>
        <label className="inline">표본 언어
          <select value={lang} onChange={(e) => setLang(e.target.value)}>
            {Object.entries(LANGUAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      {summary ? <SummaryBar s={summary} /> : <p className="muted">Steam 전체 집계를 가져오지 못했습니다.</p>}
      {q.isLoading && <Spinner label="최근 리뷰 표본을 분석하는 중…" />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && <Charts d={q.data} />}
    </section>
  )
}

function Charts({ d }: { d: ReviewStats }) {
  const s = d.sample
  if (s.size === 0) return <p className="muted">표본으로 분석할 리뷰가 없습니다.</p>
  const langs = s.languages.slice(0, 8).map((x) => ({ name: langName(x.language), count: x.count }))
  const daily = s.daily.slice(-30)
  const dateRange = s.oldest_at && s.newest_at ? `${fmtDate(s.oldest_at)} ~ ${fmtDate(s.newest_at)}` : ''
  return (
    <>
      <p className="sample-note">
        ⚠ 아래 차트는 <strong>가장 최근 리뷰 {fmtNum(s.size)}개 표본</strong>({dateRange}) 기반이며 Steam 전체 통계가 아닙니다.
        표본 긍정 비율 {s.positive_ratio != null ? `${Math.round(s.positive_ratio * 100)}%` : '-'}
        {s.median_playtime_hours != null && <> · 플레이 시간 중앙값 {s.median_playtime_hours}시간</>}
      </p>
      <div className="charts">
        <div className="chartbox">
          <h3>언어별 분포 (표본)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={langs} layout="vertical" margin={{ left: 10, right: 16 }}>
              <CartesianGrid horizontal={false} stroke="var(--line)" />
              <XAxis type="number" stroke="var(--muted)" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={96} stroke="var(--muted)" tick={{ fontSize: 12 }} />
              <Tooltip contentStyle={tip} cursor={{ fill: 'rgba(255,255,255,.05)' }} formatter={(v) => [`${v}개`, '리뷰']} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>{langs.map((_, i) => <Cell key={i} fill="var(--accent)" />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="chartbox">
          <h3>일별 리뷰 추이 (표본, 최근 {daily.length}일)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={daily} margin={{ right: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="date" stroke="var(--muted)" tick={{ fontSize: 11 }} tickFormatter={(v: string) => v.slice(5)} minTickGap={16} />
              <YAxis stroke="var(--muted)" allowDecimals={false} />
              <Tooltip contentStyle={tip} cursor={{ fill: 'rgba(255,255,255,.05)' }} />
              <Legend />
              <Bar dataKey="positive" name="추천" stackId="a" fill={POS} />
              <Bar dataKey="negative" name="비추천" stackId="a" fill={NEG} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  )
}
const tip = { background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--text)' }
