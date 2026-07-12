from fastapi import APIRouter

from app.schemas.route import RouteSummary

router = APIRouter()


@router.get("/", response_model=list[RouteSummary])
async def list_routes() -> list[RouteSummary]:
    return [
        RouteSummary(
            id="sample-route",
            name="샘플 경로",
            status="ready",
        )
    ]
