"""
Drug interaction checking router.
"""
from fastapi import APIRouter
from models.schemas import InteractionCheckRequest, InteractionResponse
from services.interactions import check_all_interactions

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("/check", response_model=InteractionResponse)
async def check_interactions(request: InteractionCheckRequest):
    """Check drug-drug interactions for a list of medications."""
    result = await check_all_interactions(request.drugs)
    return InteractionResponse(**result)
