"""Spike detection.

Media monitoring is not a thing people watch all day - they want to be told
when something breaks out. A rule compares today against the trailing average
for the same topic and mails the user when it crosses the threshold.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.database import execute, fetch_all
from app.core.elasticsearch import es_client
from app.core.es_query import SENTIMENT_FIELD, build_query
from app.services.email_service import email_service


def _count(keywords, operator, date_from: str, date_to: str, sentiment: Optional[str] = None) -> int:
    body = {"query": build_query(date_from, date_to, keywords=keywords,
                                 operator=operator, sentiment=sentiment), "size": 0}
    return es_client.search(index=settings.ELASTICSEARCH_INDEX, body=body)["hits"]["total"]["value"]


def evaluate_rule(rule: dict, today: Optional[date] = None) -> dict:
    """Compare today against the baseline window. Pure read, no side effects."""
    today = today or datetime.now(timezone.utc).date()
    days = max(int(rule["baseline_days"]), 1)
    base_from = (today - timedelta(days=days)).isoformat()
    base_to = (today - timedelta(days=1)).isoformat()
    day = today.isoformat()

    keywords, operator = rule.get("keywords") or [], rule.get("operator") or "OR"
    current = _count(keywords, operator, day, day)
    threshold = float(rule["threshold"])

    if rule["metric"] == "volume":
        baseline_total = _count(keywords, operator, base_from, base_to)
        baseline = baseline_total / days
        # A quiet topic that goes from 0 to 3 articles is not a story; without
        # this floor every such topic alerts on its first mention.
        triggered = baseline >= 1 and current >= baseline * threshold
        return {"metric": "volume", "current": current, "baseline": round(baseline, 2),
                "threshold": threshold, "triggered": triggered,
                "detail": f"{current} artikel hari ini vs rata-rata {baseline:.1f}/hari ({days} hari terakhir)"}

    negative = _count(keywords, operator, day, day, sentiment="negatif")
    share = negative / current if current else 0.0
    # Same reasoning: 1 negative article out of 1 is 100% and means nothing.
    triggered = current >= 5 and share >= threshold
    return {"metric": "negative", "current": negative, "baseline": current,
            "threshold": threshold, "triggered": triggered, "share": round(share, 3),
            "detail": f"{negative} dari {current} artikel hari ini negatif ({share:.0%})"}


def _in_cooldown(rule: dict) -> bool:
    last = rule.get("last_fired_at")
    if not last:
        return False
    return datetime.now(timezone.utc) - last < timedelta(hours=int(rule["cooldown_hours"]))


async def sweep(user_id: Optional[int] = None, send_email: bool = True) -> list:
    """Evaluate enabled rules and mail the ones that fired.

    `send_email=False` powers a "test my rules" call from the UI without
    mailing anyone.
    """
    sql = """
        SELECT r.*, t.name AS topic_name, t.keywords, t.operator, u.email AS user_email
          FROM alert_rules r
          LEFT JOIN topics t ON t.id = r.topic_id
          JOIN users u ON u.id = r.user_id
         WHERE r.enabled
    """
    args = []
    if user_id is not None:
        sql += " AND r.user_id = $1"
        args.append(user_id)

    rules = await fetch_all(sql, *args)
    fired = []

    for rule in rules:
        rule = dict(rule)
        if not rule.get("keywords"):
            # Rule points at a deleted topic, or one with no keywords: nothing
            # to measure, and counting the whole index would alert on everything.
            continue

        outcome = evaluate_rule(rule)
        outcome["rule_id"] = rule["id"]
        outcome["topic"] = rule.get("topic_name") or "-"
        outcome["cooldown"] = _in_cooldown(rule)

        if outcome["triggered"] and not outcome["cooldown"]:
            if send_email:
                to = rule.get("email_to") or rule.get("user_email")
                subject = f"[MedMon] Lonjakan {outcome['metric']} - {outcome['topic']}"
                body = (
                    f"<p>Topik <b>{outcome['topic']}</b> melewati ambang yang kamu pasang.</p>"
                    f"<p>{outcome['detail']}</p>"
                    f"<p>Ambang: {outcome['threshold']}</p>"
                )
                try:
                    await email_service.send_email(to, subject, body)
                    outcome["emailed"] = to
                except Exception as e:
                    outcome["emailed"] = f"failed: {str(e)[:120]}"
                await execute("UPDATE alert_rules SET last_fired_at = NOW() WHERE id = $1", rule["id"])
            fired.append(outcome)
        else:
            fired.append(outcome)

    return fired
