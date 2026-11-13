import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, fmtNum, type Genre, type SearchResponse } from '../api'
import { CardSkeletons, EmptyState, ErrorState, GameCard } from '../components/common'

const SORTS: [string, string][] = [
  ['relevance', '관련도순'], ['reviews', '리뷰 많은순'], ['rating', '평가 높은순'], ['newest', '최신 출시순'],
  ['oldest', '오래된순'], ['price_asc', '낮은 가격순'], ['price_desc', '높은 가격순'], ['name', '이름순'],
]
const YEAR_NOW = new Date().getFullYear()

export default function Search() {
  const [sp, setSp] = useSearchParams()
  const get = (k: string) => sp.get(k) ?? ''
  const q = get('q')
  const page = Math.max(1, Number(get('page')) || 1)
  const genre = sp.getAll('genre').map(Number).filter(Boolean)
  const sort = get('sort') || (q ? 'relevance' : 'reviews')

  const set = (patch: Record<string, string | null>) => {
    const n = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) v ? n.set(k, v) : n.delete(k)
    if (!('page' in patch)) n.delete('page')
    setSp(n)
  }
  const toggleGenre = (id: number) => {
    const n = new URLSearchParams(sp)
    n.delete('genre'); n.delete('page')
    const next = genre.includes(id) ? genre.filter((x) => x !== id) : [...genre, id]
    next.forEach((x) => n.append('genre', String(x)))
    setSp(n)
  }

  const genres = useQuery({ queryKey: ['genres'], queryFn: ({ signal }) => api<Genre[]>('/genres', undefined, signal) })
  const params = {
    q, sort, genre, page, page_size: 24,
    free: get('price') === 'free' ? true : get('price') === 'paid' ? false : null,
    price_max: get('price_max'), min_rating: get('min_rating'), min_reviews: get('min_reviews'),
    year_from: get('year_from'), year_to: get('year_to'),
  }
  const res = useQuery({
    queryKey: ['search', params],
    queryFn: ({ signal }) => api<SearchResponse>('/games/search', params, signal),
    placeholderData: keepPreviousData,
  })
  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / res.data.page_size)) : 1
  const hasFilter = ['price', 'price_max', 'min_rating', 'min_reviews', 'year_from', 'year_to'].some((k) => get(k)) || genre.length > 0

  return (
    <div className="search-layout">
      <aside className="filters" aria-label="검색 필터">
        <div className="filter-head">
          <h2>필터</h2>
          {hasFilter && <button className="link" onClick={() => setSp(new URLSearchParams(q ? { q } : {}))}>초기화</button>}
        </div>
        <label>정렬
          <select value={sort} onChange={(e) => set({ sort: e.target.value })}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <fieldset>
          <legend>장르</legend>
          <div className="chips">
            {genres.data?.map((g) => (
              <button key={g.id} className={`chip ${genre.includes(g.id) ? 'on' : ''}`} onClick={() => toggleGenre(g.id)}>{g.name}</button>
            ))}
          </div>
        </fieldset>
        <label>가격
          <select name="price" value={get('price')} onChange={(e) => set({ price: e.target.value || null })}>
            <option value="">전체</option><option value="free">무료</option><option value="paid">유료</option>
          </select>
        </label>
        <label>최대 가격 (원)
          <input type="number" min={0} step={1000} placeholder="제한 없음" defaultValue={get('price_max')} key={`pm${get('price_max')}`}
            onBlur={(e) => set({ price_max: e.target.value || null })} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
        </label>
        <label>최소 긍정 평가
          <select value={get('min_rating')} onChange={(e) => set({ min_rating: e.target.value || null })}>
            <option value="">제한 없음</option>
            {[95, 80, 70, 50].map((v) => <option key={v} value={v}>{v}% 이상</option>)}
          </select>
        </label>
        <label>최소 리뷰 수
          <select value={get('min_reviews')} onChange={(e) => set({ min_reviews: e.target.value || null })}>
            <option value="">제한 없음</option>
            {[100, 1000, 10000, 100000].map((v) => <option key={v} value={v}>{fmtNum(v)}개 이상</option>)}
          </select>
        </label>
        <div className="row2">
          <label>출시 (부터)
            <select value={get('year_from')} onChange={(e) => set({ year_from: e.target.value || null })}>
              <option value="">전체</option>
              {Array.from({ length: YEAR_NOW - 1996 }, (_, i) => YEAR_NOW - i).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label>(까지)
            <select value={get('year_to')} onChange={(e) => set({ year_to: e.target.value || null })}>
              <option value="">전체</option>
              {Array.from({ length: YEAR_NOW - 1996 }, (_, i) => YEAR_NOW - i).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </div>
        <p className="muted small">장르·평가 필터는 수집된 목록 기준이며, 평가 수치는 상세 페이지 방문 시 Steam 공식 집계로 갱신됩니다.</p>
      </aside>

      <section aria-live="polite">
        <div className="section-head">
          <h1 className="h2">{q ? <>‘{q}’ 검색 결과</> : '전체 게임'}</h1>
          {res.data && <span className="muted">{fmtNum(res.data.total)}개{res.isFetching ? ' · 갱신 중…' : ''}</span>}
        </div>
        {res.isLoading && <CardSkeletons n={12} />}
        {res.isError && <ErrorState error={res.error} onRetry={() => res.refetch()} />}
        {res.data && res.data.items.length === 0 && (
          <EmptyState title="검색 결과가 없습니다"
            hint={hasFilter ? '필터 조건을 완화해 보세요.' : '철자를 확인하거나 영어/한국어 이름의 일부만 입력해 보세요. 한국어 번역명이 없는 게임은 영어 이름으로 검색해야 합니다.'} />
        )}
        {res.data && res.data.items.length > 0 && (
          <div className={`grid ${res.isPlaceholderData ? 'dim' : ''}`}>{res.data.items.map((g) => <GameCard key={g.appid} g={g} />)}</div>
        )}
        {res.data && pages > 1 && (
          <nav className="pager" aria-label="페이지">
            <button className="btn" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>← 이전</button>
            <span>{page} / {fmtNum(pages)}</span>
            <button className="btn" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>다음 →</button>
          </nav>
        )}
      </section>
    </div>
  )
}
