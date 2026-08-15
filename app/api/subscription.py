"""Subscription API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.api.dependencies import get_current_user
from app.models.subscription import (
    SubscriptionTier,
    WorkspaceSubscriptionInfo,
    SubscriptionCheckResponse
)
from app.core.database import fetch_one, fetch_all

router = APIRouter(prefix="/subscription", tags=["subscription"])

@router.get("/tiers", response_model=List[SubscriptionTier])
async def get_subscription_tiers():
    """Get all available subscription tiers"""
    try:
        rows = await fetch_all(
            """
            SELECT id, name, display_name, description, price_monthly, price_yearly,
                   max_users, max_workspaces, historical_data_days,
                   has_reporting_access, has_api_access, trial_days
              FROM subscription_tiers
             ORDER BY price_monthly
            """
        )
        return [SubscriptionTier(**row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch subscription tiers: {str(e)}")

@router.get("/workspace-info", response_model=WorkspaceSubscriptionInfo)
async def get_workspace_subscription_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get subscription information for user's workspace"""
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="User has no workspace")
    
    try:
        # Query the workspace_subscription_info view
        row = await fetch_one(
            "SELECT * FROM workspace_subscription_info WHERE workspace_id = $1",
            workspace_id
        )

        if row is None:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")

        return WorkspaceSubscriptionInfo(**row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace subscription: {str(e)}")

@router.get("/check", response_model=SubscriptionCheckResponse)
async def check_subscription_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Check if user's workspace subscription is active"""
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="User has no workspace")
    
    try:
        row = await fetch_one(
            """
            SELECT is_expired, is_trial, subscription_tier, subscription_expires_at,
                   seconds_until_expiry, has_reporting_access, has_api_access,
                   historical_data_days, tier_display_name
              FROM workspace_subscription_info
             WHERE workspace_id = $1
            """,
            workspace_id
        )

        if row is None:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")

        is_expired = row.get("is_expired")
        message = None

        if is_expired:
            message = "Langganan Anda telah berakhir. Silakan perpanjang langganan untuk melanjutkan menggunakan MediaMon."
        
        return SubscriptionCheckResponse(
            is_expired=is_expired,
            is_trial=row.get("is_trial"),
            tier=row.get("subscription_tier"),
            expires_at=row.get("subscription_expires_at"),
            seconds_until_expiry=row.get("seconds_until_expiry"),
            has_reporting_access=row.get("has_reporting_access"),
            has_api_access=row.get("has_api_access"),
            historical_data_days=row.get("historical_data_days"),
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check subscription: {str(e)}")

@router.post("/check-access/{feature}")
async def check_feature_access(feature: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Check if user has access to a specific feature"""
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="User has no workspace")
    
    try:
        row = await fetch_one(
            """
            SELECT is_expired, has_reporting_access, has_api_access
              FROM workspace_subscription_info
             WHERE workspace_id = $1
            """,
            workspace_id
        )

        if row is None:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")

        is_expired = row.get("is_expired")
        has_reporting = row.get("has_reporting_access")
        has_api = row.get("has_api_access")
        
        if is_expired:
            raise HTTPException(
                status_code=403, 
                detail="Langganan Anda telah berakhir. Perpanjang untuk melanjutkan."
            )
        
        # Check feature access
        if feature == "reporting" and not has_reporting:
            raise HTTPException(
                status_code=403,
                detail="Fitur pelaporan tidak tersedia dalam paket Anda. Upgrade untuk mengakses."
            )
        
        if feature == "api" and not has_api:
            raise HTTPException(
                status_code=403,
                detail="Akses API tidak tersedia dalam paket Anda. Upgrade ke Pro atau lebih tinggi."
            )
        
        return {"has_access": True, "feature": feature}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check feature access: {str(e)}")
