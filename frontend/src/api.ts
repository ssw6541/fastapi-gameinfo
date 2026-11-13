const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export interface Price {
  currency: string | null
  initial?: number | null
  final: number | null
  discount_percent: number | null
  final_formatted?: string | null
}
export interface GameSummary {
  appid: number
  name: string | null
  name_en: string | null
  name_ko: string | null
  header_image: string
  capsule_image: string
  release_date: string | null
  release_ts: number | null
  is_free: boolean | null
  price: Price | null
  review_pct: number | null
  review_count: number | null
  genres: string[]
}
export interface SearchResponse {
  query: string | null
  total: number
  page: number
  page_size: number
  items: GameSummary[]
  live_discovery: boolean
}
export interface ReviewSummary {
  score_desc: string | null
  score: number | null
  total_positive: number
  total_negative: number
  total_reviews: number
  positive_ratio: number | null
}
export interface GameDetail {
  appid: number
  name: string | null
  name_en: string | null
  short_description: string
  about: string
  header_image: string
  background: string | null
  website: string | null
  is_free: boolean
  price: Price | null
  release_date: string | null
  coming_soon: boolean
  developers: string[]
  publishers: string[]
  genres: string[]
  categories: string[]
  platforms: Record<string, boolean>
  supported_languages: string
  metacritic: number | null
  recommendations: number | null
  screenshots: string[]
  movies: { name: string | null; thumbnail: string | null; url: string | null }[]
  store_url: string
  review_summary: ReviewSummary | null
  fetched_at: number | null
  stale: boolean
}
export interface Review {
  id: string
  language: string | null
  text: string
  voted_up: boolean
  votes_up: number
  votes_funny: number
  helpful_score: number
  comment_count: number
  created_at: number
  updated_at: number
  playtime_forever_min: number
  playtime_at_review_min: number
  steam_purchase: boolean
  received_for_free: boolean
  early_access: boolean
  url: string | null
}
export interface ReviewsResponse {
  appid: number
  reviews: Review[]
  cursor: string | null
  has_more: boolean
  summary: ReviewSummary | null
  cached: boolean
  fetched_at: number
}
export interface ReviewStats {
  official: ReviewSummary | null
  sample: {
    size: number
    positive: number
    negative: number
    positive_ratio: number | null
    median_playtime_hours: number | null
    oldest_at: number | null
    newest_at: number | null
    languages: { language: string; count: number }[]
    daily: { date: string; positive: number; negative: number }[]
  }
  cached: boolean
}
export interface Genre {
  id: number
  name: string
  name_en: string
  count: number
}
export interface Status {
  catalog: { games: number; with_details: number; last_updated: number | null }
  steam_api_key_configured: boolean
}

export type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>

function qs(params?: Params): string {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === null || v === undefined || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)))
    else u.set(k, String(v))
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}

export async function api<T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}/api${path}${qs(params)}`, { signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'network', '서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.')
  }
  if (!res.ok) {
    let code = 'http_error'
    let message = `요청에 실패했습니다 (${res.status})`
    try {
      const body = await res.json()
      code = body?.error?.code ?? code
      message = body?.error?.message ?? message
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message)
  }
  return (await res.json()) as T
}

export const LANGUAGES: Record<string, string> = {
  all: '모든 언어', english: '영어', koreana: '한국어', schinese: '중국어(간체)', tchinese: '중국어(번체)',
  japanese: '일본어', russian: '러시아어', german: '독일어', french: '프랑스어', spanish: '스페인어',
  latam: '스페인어(중남미)', brazilian: '포르투갈어(브라질)', portuguese: '포르투갈어', turkish: '튀르키예어',
  polish: '폴란드어', thai: '태국어', italian: '이탈리아어', ukrainian: '우크라이나어', czech: '체코어',
  dutch: '네덜란드어', swedish: '스웨덴어', vietnamese: '베트남어', arabic: '아랍어', hungarian: '헝가리어',
  romanian: '루마니아어', bulgarian: '불가리아어', danish: '덴마크어', finnish: '핀란드어', greek: '그리스어',
  norwegian: '노르웨이어', indonesian: '인도네시아어',
}

export const fmtNum = (n: number | null | undefined) => (n == null ? '-' : n.toLocaleString('ko-KR'))
export const fmtPrice = (p: Price | null, isFree: boolean | null) => {
  if (isFree) return '무료'
  if (!p || p.final == null) return '가격 정보 없음'
  if (p.final === 0) return '무료'
  return p.currency === 'KRW' || !p.currency ? `₩${Math.round(p.final).toLocaleString('ko-KR')}` : `${p.final.toFixed(2)} ${p.currency}`
}
export const fmtDate = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })
export const fmtHours = (min: number) => (min < 60 ? `${min}분` : `${(min / 60).toFixed(1)}시간`)
