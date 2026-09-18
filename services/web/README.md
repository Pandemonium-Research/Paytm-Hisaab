# Paytm Hisaab web foundation

Phone-first React/Vite PWA design system and offline shell. The component gallery is available at `/__gallery`; product screens are intentionally outside this package milestone.

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
docker build -t hisaab-web services/web
docker run --rm -p 8080:80 hisaab-web
```
