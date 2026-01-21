"""Subscription models"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SubscriptionTier(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str]
    price_monthly: int
    price_yearly: int
    max_users: int
    max_workspaces: int
    historical_data_days: int
    has_reporting_access: bool
    has_api_access: bool
    trial_days: int

class WorkspaceSubscriptionInfo(BaseModel):
    workspace_id: int
    workspace_name: Optional[str]
    subscription_tier: str
    subscription_status: str
    subscription_started_at: Optional[datetime]
    subscription_expires_at: Optional[datetime]
    is_trial: bool
    workspace_type: Optional[str]
    tier_display_name: str
    max_users: int
    max_workspaces: int
    historical_data_days: int
    has_reporting_access: bool
    has_api_access: bool
    price_monthly: int
    price_yearly: int
    is_expired: bool
    seconds_until_expiry: Optional[int]

class SubscriptionCheckResponse(BaseModel):
    is_expired: bool
    is_trial: bool
    tier: str
    expires_at: Optional[datetime]
    seconds_until_expiry: Optional[int]
    has_reporting_access: bool
    has_api_access: bool
    historical_data_days: int
    message: Optional[str]
