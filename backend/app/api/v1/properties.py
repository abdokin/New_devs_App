from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from sqlalchemy import text
import logging

from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import DatabasePool

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/properties")
async def list_properties(
    page: int = Query(1, ge=1),
    page_size: int = Query(1000, ge=1, le=5000),
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant not found")

    try:
        db_pool = DatabasePool()
        await db_pool.initialize()
        if not db_pool.session_factory:
            raise HTTPException(status_code=503, detail="Database unavailable")

        offset = (page - 1) * page_size
        search_clause = ""
        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        }
        if search:
            search_clause = " AND name ILIKE :search"
            params["search"] = f"%{search}%"

        async with (await db_pool.get_session()) as session:
            items_result = await session.execute(
                text(
                    f"""
                    SELECT id, name, timezone
                    FROM properties
                    WHERE tenant_id = :tenant_id{search_clause}
                    ORDER BY name
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
            total_result = await session.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM properties
                    WHERE tenant_id = :tenant_id{search_clause}
                    """
                ),
                params,
            )

        items = [
            {"id": row.id, "name": row.name, "timezone": row.timezone}
            for row in items_result.fetchall()
        ]
        total = total_result.scalar_one() or 0

        return {"items": items, "total": total}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load properties for tenant %s", tenant_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to load properties",
        ) from exc
