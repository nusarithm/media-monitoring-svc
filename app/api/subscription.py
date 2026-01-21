"""Subscription API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.api.dependencies import get_current_user
from app.models.subscription import (
    SubscriptionTier,
    WorkspaceSubscriptionInfo,
    SubscriptionCheckResponse
)
from app.core.database import get_supabase_service_role

router = APIRouter(prefix="/subscription", tags=["subscription"])

@router.get("/tiers", response_model=List[SubscriptionTier])
async def get_subscription_tiers():
    """Get all available subscription tiers"""
    supabase = get_supabase_service_role()
    
    try:
        result = supabase.table("subscription_tiers").select("*").order("price_monthly").execute()
        
        tiers = []
        for row in result.data:
            tiers.append(SubscriptionTier(
                id=row.get("id"),
                name=row.get("name"),
                display_name=row.get("display_name"),
                description=row.get("description"),
                price_monthly=row.get("price_monthly"),
                price_yearly=row.get("price_yearly"),
                max_users=row.get("max_users"),
                max_workspaces=row.get("max_workspaces"),
                historical_data_days=row.get("historical_data_days"),
                has_reporting_access=row.get("has_reporting_access"),
                has_api_access=row.get("has_api_access"),
                trial_days=row.get("trial_days")
            ))
        
        return tiers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch subscription tiers: {str(e)}")

@router.get("/workspace-info", response_model=WorkspaceSubscriptionInfo)
async def get_workspace_subscription_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get subscription information for user's workspace"""
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="User has no workspace")
    
    supabase = get_supabase_service_role()
    
    try:
        # Query the workspace_subscription_info view
        result = supabase.table("workspace_subscription_info").select("*").eq("workspace_id", workspace_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")
        
        row = result.data[0]
        return WorkspaceSubscriptionInfo(
            workspace_id=row.get("workspace_id"),
            workspace_name=row.get("workspace_name"),
            subscription_tier=row.get("subscription_tier"),
            subscription_status=row.get("subscription_status"),
            subscription_started_at=row.get("subscription_started_at"),
            subscription_expires_at=row.get("subscription_expires_at"),
            is_trial=row.get("is_trial"),
            workspace_type=row.get("workspace_type"),
            tier_display_name=row.get("tier_display_name"),
            max_users=row.get("max_users"),
            max_workspaces=row.get("max_workspaces"),
            historical_data_days=row.get("historical_data_days"),
            has_reporting_access=row.get("has_reporting_access"),
            has_api_access=row.get("has_api_access"),
            price_monthly=row.get("price_monthly"),
            price_yearly=row.get("price_yearly"),
            is_expired=row.get("is_expired"),
            seconds_until_expiry=row.get("seconds_until_expiry")
        )
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
    
    supabase = get_supabase_service_role()
    
    try:
        result = supabase.table("workspace_subscription_info").select(
            "is_expired, is_trial, subscription_tier, subscription_expires_at, "
            "seconds_until_expiry, has_reporting_access, has_api_access, "
            "historical_data_days, tier_display_name"
        ).eq("workspace_id", workspace_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")
        
        row = result.data[0]
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
    
    supabase = get_supabase_service_role()
    
    try:
        result = supabase.table("workspace_subscription_info").select(
            "is_expired, has_reporting_access, has_api_access"
        ).eq("workspace_id", workspace_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Workspace subscription not found")
        
        row = result.data[0]
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
