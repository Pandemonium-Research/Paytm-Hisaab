from fastapi import FastAPI

app = FastAPI(title="Hisaab fakes", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
