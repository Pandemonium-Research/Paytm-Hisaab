# Paytm Hisaab web

Phone-first React/Vite PWA with M1 Home (`/`), M2 Confirm (`/confirm`), M5 Case tracker
(`/cases`), O1 Queue (`/officer`) and O2 Review (`/officer/cases/<case_id>`).
The existing component gallery remains at `/__gallery`.

Merchant screens use `?merchant=MID_DEMO_BLR` by default; another merchant can be selected in
the query string. UI language selection is local English/Kannada; question text and chips use
core's question language. Amounts come preformatted from core.

M2 sends explicit question/transaction identity in the frozen assistant envelope through
WF31. It waits for the question read model to confirm persistence before advancing. Officer
screens approve/reject through core; WF20 handles simulated delivery after approval. PDFs
are downloaded with the officer role header.

The local defaults are `dev-app` and `dev-officer`. Build overrides are `VITE_API_BASE`,
`VITE_APP_KEY`, `VITE_OFFICER_KEY`; a session officer credential can also be set as
`hisaab-officer-key`. Core's product routes still return fixtures until A's handoff, so fixture
screens do not demonstrate persistence.

## Run locally

Requires Node 22 and npm.

```powershell
npm --prefix services/web install
npm --prefix services/web run dev
```

Open `http://localhost:5173/__gallery` to review every base component at 360 px.

## Verify and build

```powershell
npm --prefix services/web run typecheck
npm --prefix services/web run build
npm --prefix services/web run preview
```

The production build generates the 192 px and 512 px placeholder app icons, manifest, service worker, and precached offline shell in `dist/`.

## Container

```powershell
docker compose build web
docker compose --profile surfaces up -d --no-deps web
```

Open `http://localhost:8080/`. This starts web independently of the deferred memory service.
Vite development proxies `/api` to the same local Caddy origin.

Browser verification uses stateful wire-shaped API doubles and blocks external requests:

```powershell
python -m pip install --target services/web/.browser-check playwright
# Use an installed Chromium executable, or install Playwright's browser first.
$env:HISAAB_BROWSER_EXECUTABLE = 'C:/path/to/chrome.exe'
python services/web/scripts/check_mvp.py
```

Checks cover 360/412 px, answer failure/retry and read-confirmed advancement, all questions,
officer PDF/approve/reject and the sent case tracker. Screenshots are in ignored `test-results/`.
