import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtNum, fmtPrice, type GameSummary } from "../api";

const AUTOPLAY_MS = 5500;

// 616x353 capsule art carries the game's logo (stronger identity than the 460x215 header); newer apps only
// have hashed asset URLs, so fall back to the API-provided header, then hide.
const bigArt = (appid: number) =>
  `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/capsule_616x353.jpg`;
function fallback(img: HTMLImageElement, g: GameSummary) {
  const chain = [g.header_image, g.capsule_image];
  const i = Number(img.dataset.fb ?? 0);
  if (i < chain.length) {
    img.dataset.fb = String(i + 1);
    img.src = chain[i];
  } else img.style.visibility = "hidden";
}

const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Arcade "stage select" carousel: coverflow layout, autoplay, drag/swipe, keyboard, mouse tilt. */
export default function Carousel() {
  const nav = useNavigate();
  const q = useQuery({
    queryKey: ["featured", "hero"],
    queryFn: ({ signal }) =>
      api<GameSummary[]>("/games/featured", { limit: 8 }, signal),
  });
  const items = q.data ?? [];
  const n = items.length;
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [tick, setTick] = useState(0); // restarts the progress bar
  const drag = useRef<{ x: number; moved: boolean } | null>(null);
  const stage = useRef<HTMLDivElement>(null);

  const go = useCallback(
    (to: number) => {
      if (n === 0) return;
      setIdx(((to % n) + n) % n);
      setTick((t) => t + 1);
    },
    [n],
  );

  useEffect(() => {
    if (n < 2 || paused || reducedMotion()) return;
    const t = setTimeout(() => go(idx + 1), AUTOPLAY_MS);
    return () => clearTimeout(t);
  }, [idx, n, paused, tick, go]);

  if (q.isLoading)
    return (
      <div className="carousel skeleton" aria-hidden>
        <div className="cx-load">
          LOADING<span className="blink">...</span>
        </div>
      </div>
    );
  if (q.isError || n === 0) return null;

  const active = items[idx];
  const offsetOf = (i: number) => {
    let o = (i - idx) % n;
    if (o > n / 2) o -= n;
    if (o < -n / 2) o += n;
    return o;
  };

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = stage.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty(
      "--rx",
      `${((e.clientY - r.top) / r.height - 0.5) * -8}deg`,
    );
    el.style.setProperty(
      "--ry",
      `${((e.clientX - r.left) / r.width - 0.5) * 10}deg`,
    );
  };

  return (
    <section
      className="carousel"
      aria-roledescription="carousel"
      aria-label="인기 게임"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") {
          e.preventDefault();
          go(idx + 1);
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          go(idx - 1);
        } else if (e.key === "Enter" && e.target === e.currentTarget)
          nav(`/game/${active.appid}`);
      }}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => {
        setPaused(false);
        stage.current?.style.setProperty("--rx", "0deg");
        stage.current?.style.setProperty("--ry", "0deg");
      }}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      {/* blurred backdrop of the active game */}
      {items.map((g, i) => (
        <div
          key={g.appid}
          className={`cx-bg ${i === idx ? "on" : ""}`}
          style={{ backgroundImage: `url(${g.header_image})` }}
          aria-hidden
        />
      ))}

      <div className="cx-top">
        <span className="px">HIGH SCORE</span>
        <span className="px dim">
          STAGE {String(idx + 1).padStart(2, "0")}/{String(n).padStart(2, "0")}
        </span>
      </div>

      <div
        className="cx-stage"
        ref={stage}
        onMouseMove={onMove}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, moved: false };
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (d && Math.abs(e.clientX - d.x) > 50) {
            d.moved = true;
            go(idx + (e.clientX < d.x ? 1 : -1));
            suppressClick();
          }
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        {items.map((g, i) => {
          const o = offsetOf(i);
          const isActive = o === 0;
          const abs = Math.abs(o);
          return (
            <div
              key={g.appid}
              className={`cx-slide ${isActive ? "active" : ""}`}
              style={{
                transform: `translateX(calc(${o} * 52%)) scale(${1 - abs * 0.16}) ${isActive ? "rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg))" : `rotateY(${o * -14}deg)`}`,
                zIndex: 10 - abs,
                opacity: abs > 2 ? 0 : 1 - abs * 0.3,
                pointerEvents: abs > 2 ? "none" : "auto",
                filter: isActive ? "none" : "saturate(.6) brightness(.6)",
              }}
              role="group"
              aria-roledescription="slide"
              aria-label={`${i + 1} / ${n}: ${g.name}`}
              aria-hidden={abs > 2}
              onClick={(e) => {
                if (suppressed) {
                  e.preventDefault();
                  return;
                }
                if (isActive) nav(`/game/${g.appid}`);
                else go(i);
              }}
            >
              <img
                src={bigArt(g.appid)}
                alt=""
                draggable={false}
                onError={(e) => fallback(e.currentTarget, g)}
              />
              <div className="cx-shine" aria-hidden />
            </div>
          );
        })}
      </div>

      <div className="cx-info" aria-live="polite">
        <div className="cx-title">
          <h2>{active.name}</h2>
          {active.name_ko && active.name_en && (
            <span className="muted">{active.name_en}</span>
          )}
        </div>
        <div className="cx-stats">
          <span className="px-stat">
            <small>SCORE</small>
            {active.review_pct != null ? `${active.review_pct}%` : "--"}
          </span>
          <span className="px-stat">
            <small>REVIEWS</small>
            {fmtNum(active.review_count)}
          </span>
          <span className="px-stat">
            <small>PRICE</small>
            {fmtPrice(active.price, active.is_free)}
          </span>
        </div>
        <button
          className="btn primary arcade-btn"
          onClick={() => nav(`/game/${active.appid}`)}
        >
          ▶ PRESS START
        </button>
      </div>

      <div className="cx-ctrl">
        <button
          className="cx-arrow"
          aria-label="이전 게임"
          onClick={() => go(idx - 1)}
        >
          ◀
        </button>
        <div className="cx-dots" role="tablist" aria-label="게임 선택">
          {items.map((g, i) => (
            <button
              key={g.appid}
              role="tab"
              aria-selected={i === idx}
              aria-label={g.name ?? ""}
              className={`cx-dot ${i === idx ? "on" : ""}`}
              onClick={() => go(i)}
            >
              {i === idx && !paused && !reducedMotion() && (
                <span
                  key={tick}
                  className="cx-fill"
                  style={{ animationDuration: `${AUTOPLAY_MS}ms` }}
                />
              )}
            </button>
          ))}
        </div>
        <button
          className="cx-arrow"
          aria-label="다음 게임"
          onClick={() => go(idx + 1)}
        >
          ▶
        </button>
      </div>
    </section>
  );
}

// A drag ends with a click on the slide under the pointer; swallow that one click.
let suppressed = false;
function suppressClick() {
  suppressed = true;
  setTimeout(() => {
    suppressed = false;
  }, 0);
}
