# -*- coding: utf-8 -*-
"""公开商业套餐和专项服务说明。"""
from fastapi import APIRouter

from commercial_service import get_commercial_catalog


router = APIRouter(prefix="/api/commercial", tags=["商业套餐"])


@router.get("/offers")
def commercial_offers():
    return get_commercial_catalog()
