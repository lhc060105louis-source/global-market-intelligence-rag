# -*- coding: utf-8 -*-
"""公开产品定位与用户场景。"""
from fastapi import APIRouter

from positioning_service import get_product_positioning


router = APIRouter(prefix="/api/product", tags=["产品定位"])


@router.get("/positioning")
def product_positioning():
    return get_product_positioning()
