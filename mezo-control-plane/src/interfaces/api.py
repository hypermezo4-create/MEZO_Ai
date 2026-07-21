from fastapi import APIRouter

router = APIRouter(prefix="/control", tags=["control"])

@router.get("/status")
def control_status():
    return {"status": "ok", "plane": "MEZO Control Plane"}
