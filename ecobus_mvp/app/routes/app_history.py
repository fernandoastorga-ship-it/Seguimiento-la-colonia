from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import desc, func, select

from app.db import get_db
from app.models import Checkin
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/history", tags=["App History"])

security = HTTPBearer()


@router.get("/")
def get_my_history(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        total_stmt = (
            select(func.count())
            .select_from(Checkin)
            .where(Checkin.passenger_id == passenger.id)
        )
        total = db.execute(total_stmt).scalar_one()

        stmt = (
            select(Checkin)
            .where(Checkin.passenger_id == passenger.id)
            .order_by(desc(Checkin.created_at), desc(Checkin.id))
            .offset(offset)
            .limit(limit)
        )

        rows = db.execute(stmt).scalars().all()

        items = []
        for c in rows:
            items.append(
                {
                    "id": c.id,
                    "created_at": c.created_at,
                    "service_date": c.service_date,
                    "trip_type": c.trip_type.value if c.trip_type else None,
                    "pickup_point": c.pickup_point.value if c.pickup_point else None,
                    "result": c.result.value if c.result else None,
                    "reason": c.reason,
                    "entitlement": c.entitlement,
                }
            )

        return {
            "passenger": {
                "id": str(passenger.id),
                "full_name": passenger.full_name,
            },
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(items),
            },
            "items": items,
        }
