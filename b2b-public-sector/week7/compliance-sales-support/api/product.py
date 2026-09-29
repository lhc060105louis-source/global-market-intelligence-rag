# -*- coding: utf-8 -*-
"""Public product positioning and use cases."""
from fastapi import APIRouter

from positioning_service import get_product_positioning


router = APIRouter(prefix="/api/product", tags=["Product Positioning"])


@router.get("/positioning")
def product_positioning():
    return get_product_positioning()
