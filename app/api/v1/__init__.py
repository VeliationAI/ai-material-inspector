from fastapi import APIRouter

from app.api.v1 import auth, inspections, purchase_orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(purchase_orders.router, prefix="/purchase-orders", tags=["purchase-orders"])
api_router.include_router(inspections.router, prefix="/inspections", tags=["inspections"])
