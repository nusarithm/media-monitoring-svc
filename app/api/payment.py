import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
from app.api.dependencies import get_current_user
from app.core.database import fetch_one, fetch_all, get_pool
from app.services.email_service import email_service

router = APIRouter()

# Saweria posts here directly, so it is mounted at the root, not under /api/payment
webhook_router = APIRouter(prefix="/webhook", tags=["Webhook"])


class PaymentRequest(BaseModel):
    """Payment request model"""
    amount: Optional[int] = None
    message: Optional[str] = None
    email: Optional[str] = None
    # Add other fields as needed based on Saweria API requirements


@router.post("/create")
async def create_payment(
    payment_data: Dict[str, Any],
):
    """
    Create payment via Saweria backend
    Proxies request to Saweria payment gateway
    """
    try:
        # Saweria backend URL
        url_payment = "https://backend.saweria.co/donations/snap/b291400e-2cc7-4b32-a642-6e22e2eb8704"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url_payment,
                json=payment_data,
                headers={
                    'Content-Type': 'application/json',
                },
                timeout=30.0
            )
            
            if response.status_code != 201:
                error_detail = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": "Payment request failed",
                        "details": error_detail
                    }
                )
            
            data = response.json()
            return data
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "Payment gateway timeout", "message": "Request to payment gateway timed out"}
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "Payment gateway error", "message": str(e)}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)}
        )


@router.get("/history")
async def get_payment_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Payment history for the caller's own workspace.

    The workspace comes from the token, never from a query parameter, so one
    workspace cannot read another's billing records.
    """
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="User has no workspace")

    workspace = await fetch_one(
        """
        SELECT w.id, w.workspace_name, w.subscription_tier, w.subscription_status,
               w.subscription_started_at, w.subscription_expires_at, w.is_trial,
               st.display_name, st.price_monthly, st.price_yearly, st.max_users,
               st.max_workspaces, st.historical_data_days,
               st.has_reporting_access, st.has_api_access
          FROM workspace w
          LEFT JOIN subscription_tiers st ON w.subscription_tier = st.name
         WHERE w.id = $1
        """,
        workspace_id
    )

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    history = await fetch_all(
        """
        SELECT id, created_at, transaction_id, payment_type, subscription_tier,
               billing_period, amount_raw, amount_to_display, donator_name,
               donator_email, status, payment_created_at
          FROM payment_history
         WHERE workspace_id = $1
         ORDER BY created_at DESC
        """,
        workspace_id
    )

    return {
        "success": True,
        "workspace": {
            "id": workspace["id"],
            "name": workspace["workspace_name"],
            "subscription_tier": workspace["subscription_tier"],
            "subscription_status": workspace["subscription_status"],
            "subscription_started_at": workspace["subscription_started_at"],
            "subscription_expires_at": workspace["subscription_expires_at"],
            "is_trial": workspace["is_trial"],
            "tier_details": {
                "display_name": workspace["display_name"],
                "price_monthly": workspace["price_monthly"],
                "price_yearly": workspace["price_yearly"],
                "max_users": workspace["max_users"],
                "max_workspaces": workspace["max_workspaces"],
                "historical_data_days": workspace["historical_data_days"],
                "has_reporting_access": workspace["has_reporting_access"],
                "has_api_access": workspace["has_api_access"],
            },
        },
        "payment_history": history,
    }


@router.get("/status/{transaction_id}")
async def get_payment_status(transaction_id: str):
    """
    Poll the status of one transaction. Unauthenticated: the checkout modal
    polls this while the user is still completing payment.
    """
    payment = await fetch_one(
        """
        SELECT status, workspace_id, subscription_tier, billing_period
          FROM payment_history
         WHERE transaction_id = $1
        """,
        transaction_id
    )

    if payment is None:
        return {"found": False, "status": "PENDING"}

    return {
        "found": True,
        "status": payment["status"],
        "workspace_id": payment["workspace_id"],
        "subscription_tier": payment["subscription_tier"],
        "billing_period": payment["billing_period"],
    }


@webhook_router.post("/payment")
async def payment_webhook(payload: Dict[str, Any]):
    """
    Saweria payment webhook.

    The plan is carried in the donation message as "tier-period-workspace_id",
    e.g. "basic-monthly-16".
    """
    message = str(payload.get("message") or "")
    parts = message.split("-")
    if len(parts) < 3:
        raise HTTPException(
            status_code=400,
            detail="Invalid message format. Expected: tier-period-workspace_id"
        )

    subscription_tier, billing_period = parts[0], parts[1]

    try:
        workspace_id = int(parts[2])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace ID in message")

    if billing_period not in ("monthly", "yearly"):
        raise HTTPException(
            status_code=400,
            detail="Invalid billing period. Must be monthly or yearly"
        )

    workspace = await fetch_one("SELECT id FROM workspace WHERE id = $1", workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    tier = await fetch_one(
        "SELECT name, display_name FROM subscription_tiers WHERE name = $1",
        subscription_tier
    )
    if tier is None:
        raise HTTPException(status_code=404, detail="Subscription tier not found")

    etc = payload.get("etc") or {}
    months = 1 if billing_period == "monthly" else 12

    # created_at arrives as an ISO string; asyncpg needs a real datetime
    payment_created_at = payload.get("created_at")
    if isinstance(payment_created_at, str):
        try:
            payment_created_at = datetime.fromisoformat(payment_created_at)
        except ValueError:
            payment_created_at = None

    # Record the payment and move the subscription forward together, so a
    # failure cannot leave a paid record with an unextended subscription.
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Returns None when this transaction was already processed, which
            # keeps a webhook retry from extending the subscription twice.
            inserted = await conn.fetchval(
                """
                INSERT INTO payment_history (
                    transaction_id, payment_type, workspace_id, subscription_tier,
                    billing_period, amount_raw, amount_to_display, cut,
                    transaction_fee_policy, donator_name, donator_email,
                    donator_is_user, message, qr_string, status, webhook_payload,
                    payment_created_at
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'COMPLETED',$15,$16)
                ON CONFLICT (transaction_id) DO NOTHING
                RETURNING id
                """,
                payload.get("id"), payload.get("type"), workspace_id, subscription_tier,
                billing_period, payload.get("amount_raw"), etc.get("amount_to_display"),
                payload.get("cut"), etc.get("transaction_fee_policy"),
                payload.get("donator_name"), payload.get("donator_email"),
                payload.get("donator_is_user"), message, etc.get("qr_string"),
                json.dumps(payload), payment_created_at
            )

            if inserted is None:
                current = await conn.fetchval(
                    "SELECT subscription_expires_at FROM workspace WHERE id = $1",
                    workspace_id
                )
                return {
                    "success": True,
                    "message": "Payment already processed",
                    "data": {
                        "workspace_id": workspace_id,
                        "subscription_tier": subscription_tier,
                        "billing_period": billing_period,
                        "expires_at": current.isoformat() if current else None,
                    },
                }

            expires_at = await conn.fetchval(
                """
                UPDATE workspace
                   SET subscription_tier = $2,
                       subscription_started_at = NOW(),
                       subscription_expires_at = NOW() + make_interval(months => $3),
                       subscription_status = 'active',
                       is_trial = FALSE
                 WHERE id = $1
                RETURNING subscription_expires_at
                """,
                workspace_id, subscription_tier, months
            )

    # Email failure must not fail the webhook - Saweria would keep retrying.
    if payload.get("donator_email"):
        try:
            await email_service.send_payment_success_email(
                to_email=payload["donator_email"],
                name=payload.get("donator_name") or payload["donator_email"],
                plan_name=tier["display_name"],
                amount=payload.get("amount_raw") or 0,
                billing_period=billing_period,
                expires_at=expires_at.isoformat()
            )
        except Exception as e:
            print(f"Failed to send payment success email: {e}")

    return {
        "success": True,
        "message": "Payment processed successfully",
        "data": {
            "workspace_id": workspace_id,
            "subscription_tier": subscription_tier,
            "billing_period": billing_period,
            "expires_at": expires_at.isoformat(),
        },
    }
