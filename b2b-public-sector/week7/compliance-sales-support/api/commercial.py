# -*- coding: utf-8 -*-
"""Public commercial plans and specialist service descriptions."""
from fastapi import APIRouter

from commercial_service import get_commercial_catalog


router = APIRouter(prefix="/api/commercial", tags=["Commercial Offers"])


@router.get("/offers")
def commercial_offers():
    return get_commercial_catalog()
