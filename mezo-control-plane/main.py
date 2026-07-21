from fastapi import FastAPI
from src.interfaces.api import router as api_router
from src.interfaces.webhook import router as webhook_router

app = FastAPI(title="MEZO Control Plane Engine", version="1.0.0")

app.include_router(api_router)
app.include_router(webhook_router)

@app.get("/")
def read_root():
    return {"service": "MEZO Control Plane", "status": "running"}
