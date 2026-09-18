from fastapi import FastAPI

from .sarvam import router as sarvam_router
from .twilio import router as twilio_router

app = FastAPI(title="Hisaab fakes", version="0.1.0")
app.include_router(sarvam_router)
app.include_router(twilio_router)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
