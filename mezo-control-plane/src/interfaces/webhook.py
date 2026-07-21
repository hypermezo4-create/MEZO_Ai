from fastapi import APIRouter, Request

router = APIRouter(prefix="/webhook", tags=["webhook"])

@router.post("/event")
async def receive_event(request: Request):
    payload = await request.json()
    return {"status": "received", "event": payload.get("event")}
