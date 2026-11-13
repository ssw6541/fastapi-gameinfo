import { Suspense, lazy, useEffect } from 'react'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import Topbar from './components/Topbar'
import { EmptyState, Spinner } from './components/common'
import Home from './pages/Home'
import Search from './pages/Search'

const Game = lazy(() => import('./pages/Game')) // keeps charts out of the initial bundle

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <>
      <Topbar />
      <main className="container">
        <Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<Search />} />
          <Route path="/game/:appid" element={<Game />} />
          <Route
            path="*"
            element={<EmptyState title="페이지를 찾을 수 없습니다" hint="주소를 확인하거나 홈에서 게임을 검색해 보세요." action={<Link className="btn" to="/">홈으로</Link>} />}
          />
        </Routes>
        </Suspense>
      </main>
      <footer className="footer container">
        <p>
          GameLens는 Steam 공식 API 데이터를 사용하는 비공식 정보 사이트입니다. Steam 및 관련 상표는 Valve Corporation의 자산이며,
          게임 이미지·리뷰의 권리는 각 권리자에게 있습니다.
        </p>
      </footer>
    </>
  )
}
