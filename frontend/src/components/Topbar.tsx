import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ApiError, api, type Me } from "../api";
import SearchBox from "./SearchBox";

const MENU: { to: string; label: string; hint: string }[] = [
  { to: "/", label: "홈", hint: "HOME" },
  { to: "/?tab=popular", label: "인기 게임", hint: "RANKING" },
  { to: "/?tab=new", label: "신작", hint: "NEW" },
  { to: "/?tab=sale", label: "할인 중", hint: "SALE" },
  { to: "/?tab=upcoming", label: "출시 예정", hint: "SOON" },
  { to: "/search?sort=reviews", label: "전체 게임 검색", hint: "ALL" },
];

/** Closes `open` on outside click / Escape. */
function useDismiss(
  ref: React.RefObject<HTMLElement | null>,
  open: boolean,
  close: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open, close, ref]);
}

function MenuButton() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { pathname, search } = useLocation();
  useEffect(() => {
    setOpen(false);
  }, [pathname, search]);
  useDismiss(ref, open, () => setOpen(false));
  return (
    <div className="menu" ref={ref}>
      <button
        className="btn menu-btn"
        aria-label="메뉴"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="burger" aria-hidden>
          {open ? "✕" : "☰"}
        </span>
        <span className="px">MENU</span>
      </button>
      {open && (
        <nav className="menu-pop" aria-label="주요 메뉴">
          {MENU.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              end
              className="menu-item"
              onClick={() => setOpen(false)}
            >
              <span>{m.label}</span>
              <span className="px dim">{m.hint}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}

function Account() {
  const qc = useQueryClient();
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, open, () => setOpen(false));
  const me = useQuery({
    queryKey: ["me"],
    queryFn: ({ signal }) => api<Me>("/auth/me", undefined, signal),
    staleTime: 300_000,
    retry: false,
  });
  const logout = useMutation({
    mutationFn: () =>
      fetch("/api/auth/logout", { method: "POST" }).then((r) => {
        if (!r.ok) throw new ApiError(r.status, "http_error", "로그아웃 실패");
      }),
    onSuccess: () => {
      setOpen(false);
      qc.setQueryData(["me"], { logged_in: false });
    },
  });
  const next = encodeURIComponent(pathname + search);

  if (me.data?.logged_in) {
    return (
      <div className="account" ref={ref}>
        <button
          className="btn acct-btn"
          aria-haspopup="true"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {me.data.avatar ? (
            <img src={me.data.avatar} alt="" width={22} height={22} />
          ) : (
            <span aria-hidden>👤</span>
          )}
          <span className="acct-name">{me.data.name ?? "Steam 사용자"}</span>
        </button>
        {open && (
          <div className="menu-pop right">
            <a
              className="menu-item"
              href={me.data.profile_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span>내 Steam 프로필 ↗</span>
            </a>
            <a className="menu-item" href="steam://open/main">
              <span>Steam 앱 열기</span>
            </a>
            <button
              className="menu-item"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
            >
              <span>로그아웃</span>
            </button>
          </div>
        )}
      </div>
    );
  }
  return (
    <a
      className="btn steam-login"
      href={`/api/auth/steam/login?next=${next}`}
      title="Steam 공식 로그인 페이지로 이동합니다. 비밀번호는 이 사이트에 전달되지 않습니다."
    >
      <span aria-hidden>🎮</span>{" "}
      <span className="login-txt">Steam 로그인</span>
    </a>
  );
}

export default function Topbar() {
  return (
    <header className="topbar">
      <div className="container topbar-in">
        <Link to="/" className="brand" aria-label="GameLens 홈">
          <span className="logo" aria-hidden>
            ◆
          </span>{" "}
          <span className="px">GAMELENS</span>
        </Link>
        <nav className="topnav" aria-label="바로가기">
          {MENU.slice(1, 5).map((m) => (
            <NavLink key={m.to} to={m.to} end>
              {m.label}
            </NavLink>
          ))}
        </nav>
        <div className="topsearch">
          <SearchBox compact />
        </div>
        <div className="topbar-right">
          <MenuButton />
          <Account />
        </div>
      </div>
    </header>
  );
}
