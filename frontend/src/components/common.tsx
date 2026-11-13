import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, fmtNum, fmtPrice, type GameSummary } from "../api";

/** Try each fallback URL in order when an image 404s (newer Steam apps use hashed URLs), then hide it. */
export function imgFallback(img: HTMLImageElement, ...alts: string[]) {
  const i = Number(img.dataset.fb ?? 0)
  const next = alts.filter(Boolean)[i]
  if (next) { img.dataset.fb = String(i + 1); img.src = next } else img.style.visibility = 'hidden'
}

export function Spinner({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" /> {label}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state-icon" aria-hidden>
        ◇
      </div>
      <h2>{title}</h2>
      {hint && <p>{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const e = error instanceof ApiError ? error : null;
  let title = "문제가 발생했습니다";
  if (e?.code === "network") title = "서버에 연결할 수 없습니다";
  else if (e?.code === "not_found") title = "찾을 수 없습니다";
  else if (e?.code?.startsWith("steam"))
    title = "Steam에서 데이터를 가져오지 못했습니다";
  else if (e?.status === 429) title = "요청이 너무 많습니다";
  return (
    <div className="state error" role="alert">
      <div className="state-icon" aria-hidden>
        !
      </div>
      <h2>{title}</h2>
      <p>
        {e?.message ?? "알 수 없는 오류입니다. 잠시 후 다시 시도해 주세요."}
      </p>
      {onRetry && e?.code !== "not_found" && (
        <button className="btn" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}

export function ReviewBadge({
  pct,
  count,
}: {
  pct: number | null;
  count: number | null;
}) {
  if (pct == null || !count)
    return <span className="muted small">평가 없음</span>;
  const tone = pct >= 70 ? "good" : pct >= 40 ? "mixed" : "bad";
  return (
    <span
      className={`rbadge ${tone}`}
      title={`긍정 ${pct}% · 리뷰 ${fmtNum(count)}개`}
    >
      {pct}% <small>({fmtNum(count)})</small>
    </span>
  );
}

export function GameCard({ g }: { g: GameSummary }) {
  const p = g.price;
  const disc = p?.discount_percent ?? 0;
  return (
    <Link to={`/game/${g.appid}`} className="card">
      <div className="card-img">
        <img
          src={g.header_image}
          alt=""
          loading="lazy"
          onError={(e) => imgFallback(e.currentTarget, g.capsule_image)}
        />
        {disc > 0 && <span className="disc">-{disc}%</span>}
      </div>
      <div className="card-body">
        <h3 title={g.name ?? ""}>{g.name ?? `App ${g.appid}`}</h3>
        {g.name_ko && g.name_en && <div className="sub">{g.name_en}</div>}
        <div className="card-meta">
          <ReviewBadge pct={g.review_pct} count={g.review_count} />
          <span className="price">{fmtPrice(p, g.is_free)}</span>
        </div>
        <div className="card-foot">
          <span>{g.release_date ?? "출시일 미상"}</span>
          {g.genres.length > 0 && (
            <span className="tags">{g.genres.slice(0, 2).join(" · ")}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

export function CardSkeletons({ n = 8 }: { n?: number }) {
  return (
    <div className="grid" aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="card skel">
          <div className="card-img" />
          <div className="card-body">
            <div className="sk-line" />
            <div className="sk-line short" />
          </div>
        </div>
      ))}
    </div>
  );
}
