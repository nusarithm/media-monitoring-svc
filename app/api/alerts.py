"""Alert rules: create thresholds, run them on demand, see what would fire."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.database import execute, fetch_all, fetch_one
from app.services.alert_service import sweep

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class AlertRuleIn(BaseModel):
    topic_id: int
    metric: str = Field(..., pattern="^(volume|negative)$")
    # volume: multiple of the baseline (2 = twice the daily average)
    # negative: share of today's articles that are negative (0.4 = 40%)
    threshold: float = Field(..., gt=0)
    baseline_days: int = Field(7, ge=1, le=90)
    email_to: Optional[str] = None
    enabled: bool = True
    cooldown_hours: int = Field(12, ge=1, le=168)


class AlertRule(AlertRuleIn):
    id: int
    topic_name: Optional[str] = None
    last_fired_at: Optional[str] = None


@router.get("", response_model=List[AlertRule])
async def list_rules(current_user: dict = Depends(get_current_active_user)):
    rows = await fetch_all(
        """
        SELECT r.id, r.topic_id, r.metric, r.threshold::float AS threshold, r.baseline_days,
               r.email_to, r.enabled, r.cooldown_hours, r.last_fired_at::text AS last_fired_at,
               t.name AS topic_name
          FROM alert_rules r
          LEFT JOIN topics t ON t.id = r.topic_id
         WHERE r.user_id = $1
         ORDER BY r.id
        """,
        current_user["id"],
    )
    return rows


@router.post("", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_rule(body: AlertRuleIn, current_user: dict = Depends(get_current_active_user)):
    owns = await fetch_one("SELECT id FROM topics WHERE id = $1 AND user_id = $2",
                           body.topic_id, current_user["id"])
    if owns is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    row = await fetch_one(
        """
        INSERT INTO alert_rules (user_id, topic_id, metric, threshold, baseline_days,
                                 email_to, enabled, cooldown_hours)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, topic_id, metric, threshold::float AS threshold, baseline_days,
                  email_to, enabled, cooldown_hours, last_fired_at::text AS last_fired_at
        """,
        current_user["id"], body.topic_id, body.metric, body.threshold,
        body.baseline_days, body.email_to, body.enabled, body.cooldown_hours,
    )
    return row


@router.put("/{rule_id}", response_model=AlertRule)
async def update_rule(rule_id: int, body: AlertRuleIn, current_user: dict = Depends(get_current_active_user)):
    row = await fetch_one(
        """
        UPDATE alert_rules
           SET topic_id = $3, metric = $4, threshold = $5, baseline_days = $6,
               email_to = $7, enabled = $8, cooldown_hours = $9, updated_at = NOW()
         WHERE id = $1 AND user_id = $2
        RETURNING id, topic_id, metric, threshold::float AS threshold, baseline_days,
                  email_to, enabled, cooldown_hours, last_fired_at::text AS last_fired_at
        """,
        rule_id, current_user["id"], body.topic_id, body.metric, body.threshold,
        body.baseline_days, body.email_to, body.enabled, body.cooldown_hours,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return row


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, current_user: dict = Depends(get_current_active_user)):
    result = await execute("DELETE FROM alert_rules WHERE id = $1 AND user_id = $2",
                           rule_id, current_user["id"])
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.post("/check")
async def check_rules(
    send_email: bool = False,
    current_user: dict = Depends(get_current_active_user),
):
    """Evaluate this user's rules now.

    Defaults to a dry run so the UI can show "this is what would fire" without
    mailing anyone; pass send_email=true to actually send.
    """
    try:
        return {"results": await sweep(user_id=current_user["id"], send_email=send_email)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Alert check failed: {str(e)}")
