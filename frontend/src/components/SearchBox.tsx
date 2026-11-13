import { useQuery } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type GameSummary } from '../api'

function useDebounced<T>(v: T, ms: number) {
  const [d, setD] = useState(v)
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms)
    return () => clearTimeout(t)
  }, [v, ms])
  return d
}

export default function SearchBox({ compact = false, autoFocus = false }: { compact?: boolean; autoFocus?: boolean }) {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const box = useRef<HTMLDivElement>(null)
  const listId = useId()
  const q = useDebounced(text.trim(), 250)

  const sug = useQuery({
    queryKey: ['suggest', q],
    queryFn: ({ signal }) => api<GameSummary[]>('/games/suggest', { q }, signal),
    enabled: q.length >= 1 && open,
    staleTime: 300_000,
  })

  useEffect(() => {
    const h = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const t = text.trim()
    if (!t) return
    setOpen(false)
    nav(`/search?q=${encodeURIComponent(t)}`)
  }
  const items = sug.data ?? []

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, -1)) }
    else if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'Enter' && active >= 0 && items[active]) {
      e.preventDefault(); setOpen(false); nav(`/game/${items[active].appid}`)
    }
  }

  return (
    <div className={`searchbox ${compact ? 'compact' : ''}`} ref={box}>
      <form onSubmit={submit} role="search">
        <input
          type="search"
          value={text}
          maxLength={100}
          autoFocus={autoFocus}
          placeholder="게임 이름 검색 (예: Elden Ring, 서브노티카)"
          aria-label="게임 검색"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={open}
          onChange={(e) => { setText(e.target.value); setOpen(true); setActive(-1) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
        <button className="btn primary" type="submit">검색</button>
      </form>
      {open && q.length >= 1 && (
        <ul className="suggest" id={listId} role="listbox">
          {sug.isFetching && items.length === 0 && <li className="muted pad">검색 중…</li>}
          {sug.isError && <li className="muted pad">자동완성을 불러오지 못했습니다.</li>}
          {!sug.isFetching && !sug.isError && items.length === 0 && <li className="muted pad">일치하는 게임이 없습니다.</li>}
          {items.map((g, i) => (
            <li key={g.appid} role="option" aria-selected={i === active} className={i === active ? 'active' : ''}
              onMouseDown={(e) => { e.preventDefault(); setOpen(false); nav(`/game/${g.appid}`) }}>
              <img src={g.capsule_image} alt="" loading="lazy" />
              <span className="sname">{g.name}{g.name_ko && g.name_en ? <small> {g.name_en}</small> : null}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
