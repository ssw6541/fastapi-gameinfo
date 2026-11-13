# GameLens — Steam 게임 정보 & 리뷰 검색

FastAPI(Uvicorn) 백엔드 + Vite/React/TypeScript 프론트엔드. 영/한 게임명 부분일치 검색, 상세 정보, Steam 공식 리뷰(커서 페이지네이션·필터), 리뷰 통계 차트.

## 구조
```
backend/   FastAPI (app/api 라우터, app/services 비즈니스 로직, app/steam 클라이언트+변환 계층, migrations/*.sql, tests/)
frontend/  Vite + React + TS (TanStack Query, React Router, Recharts, Playwright e2e)
docs/      추가 문서
start-dev.ps1  Windows 개발 서버 실행 스크립트
```
저장소: SQLite(WAL) + FTS5 trigram 인덱스(부분일치, 한글 포함). 캐시: 메모리 + SQLite `kv_cache`. `DATABASE_PATH`만 바꿔 파일 위치 변경 가능(운영 확장 시 PostgreSQL 이전 권장).

## 실행
요구사항: Python 3.11+, Node 20+.
```powershell
.\start-dev.ps1        # venv/의존성/.env 준비 후 두 서버 실행
```
수동: `cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt; copy .env.example .env; .venv\Scripts\python -m uvicorn app.main:app --reload` / `cd frontend; npm i; npm run dev`
- 프론트 http://localhost:5173 (dev 프록시가 /api → :8000), API 문서 http://localhost:8000/docs

## 환경변수
`backend/.env.example`, `frontend/.env.example` 참고. `STEAM_API_KEY`는 선택(전체 앱 목록 `IStoreService/GetAppList` 수집 전용, https://steamcommunity.com/dev/apikey 에서 발급). 백엔드에만 두며 로그에서 마스킹됩니다. `VITE_*` 값은 브라우저에 공개됩니다. `ADMIN_TOKEN`을 설정해야 `/api/admin/*`(X-Admin-Token 헤더)가 활성화됩니다.

## Steam 로그인
Steam 공식 OpenID 로그인(`/api/auth/steam/login`)을 사용합니다. 비밀번호는 이 앱에 전달되지 않고, 앱은 SteamID만 서명된 HttpOnly 쿠키로 보관합니다. `PUBLIC_BASE_URL`(사용자가 보는 사이트 주소)과 `SESSION_SECRET`을 설정해야 하며, Vercel 프록시 사용 시 쿠키가 Vercel 도메인에 설정됩니다.

## 데이터 수집
```powershell
cd backend
.venv\Scripts\python -m app.cli crawl-search --max-games 10000   # 키 불필요, 중단 후 재개 가능
.venv\Scripts\python -m app.cli crawl-applist                    # STEAM_API_KEY 필요
.venv\Scripts\python -m app.cli refresh-details --limit 50
.venv\Scripts\python -m app.cli stats
```
목록에 없는 게임은 검색 시 Steam `storesearch`로 즉시 발견·저장됩니다. 상세는 조회 시 저장/갱신(24h).

## 테스트
```powershell
cd backend; .venv\Scripts\python -m pytest          # Steam 모의 응답 기반 단위/API 테스트
cd frontend; npm run build; npx playwright test     # 실제 백엔드+Steam 대상 E2E (서버 자동 기동)
```

## 확인된 Steam 제약 (2026-11 실측)
- `IStoreService/GetAppList`는 키 없이 403. `ISteamApps/GetAppList/v2`는 사용하지 않음.
- `IUserReviewsService/GetAppReviews/v1`은 키 없이 동작하며 `languages[]`(배열)와 enum 정수(filter/review_type/purchase_type)를 사용. 구 `language` 파라미터는 무시되어 영어만 반환됨. 점수 합계(`query_summary`)는 필터 없는 첫 페이지에만 포함 → 별도 호출·캐시. 합계는 언어 필터와 무관.
- 스토어 검색 목록(`/search/results`)은 약 60페이지 연속 호출 후 429 → 클라이언트가 백오프, 크롤러는 중단 후 재개.
- Steam이 한국어 제목을 제공하지 않는 게임(예: ELDEN RING)은 한글로 검색되지 않음(영문명으로 검색).
- 리뷰 통계의 언어 분포/추이는 최근 리뷰 표본 기반이며 UI에 표본임을 명시.

출처: partner.steamgames.com/doc/webapi/{IStoreService,IUserReviewsService}, /doc/webapi_overview, steamcommunity.com/dev/apiterms.

## 향후 개선
PostgreSQL 이전, 정기 갱신 스케줄러, 한글 별칭 사전, 태그 기반 필터 확장, 리뷰 표본 장기 저장.
