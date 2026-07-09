from calendar import monthrange
from datetime import UTC, datetime

from app.core.supabase_client import get_service_client

STAGES = ["novo_lead", "em_atendimento", "negociacao", "fechamento", "pos_venda"]


def _month_bounds(reference: datetime) -> tuple[str, str]:
    start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(reference.year, reference.month)[1]
    end = reference.replace(day=last_day, hour=23, minute=59, second=59)
    return start.isoformat(), end.isoformat()


def _prev_month_reference(reference: datetime) -> datetime:
    if reference.month == 1:
        return reference.replace(year=reference.year - 1, month=12)
    return reference.replace(month=reference.month - 1)


def get_metrics(tenant_id: str) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC)
    month_start, month_end = _month_bounds(now)
    prev_start, prev_end = _month_bounds(_prev_month_reference(now))

    contacts = sb.table("contacts").select("*").eq("tenant_id", tenant_id).execute().data
    deals = sb.table("deals").select("*").eq("tenant_id", tenant_id).execute().data

    new_leads_month = sum(1 for c in contacts if month_start <= c["first_contact_at"] <= month_end)

    in_negotiation_value = sum(
        d["value"] for d in deals if d["outcome"] == "aberto" and d["stage"] in ("negociacao", "fechamento")
    )

    won_deals = [d for d in deals if d["outcome"] == "ganho"]
    revenue_month = sum(d["value"] for d in won_deals if month_start <= d["stage_changed_at"] <= month_end)
    revenue_prev_month = sum(d["value"] for d in won_deals if prev_start <= d["stage_changed_at"] <= prev_end)
    net_profit_month = sum(
        d["value"] - (d.get("supplier_value") or 0) - (d.get("gift_value") or 0)
        for d in won_deals
        if month_start <= d["stage_changed_at"] <= month_end
    )

    lost_count = sum(1 for d in deals if d["outcome"] == "perdido")
    won_count = len(won_deals)
    decided = won_count + lost_count
    conversion_rate = round((won_count / decided) * 1000) / 10 if decided else 0.0

    funnel_counts = []
    for stage in STAGES:
        stage_deals = [d for d in deals if d["outcome"] != "perdido" and d["stage"] == stage]
        funnel_counts.append({"stage": stage, "count": len(stage_deals), "value": sum(d["value"] for d in stage_deals)})

    origins = sorted({c["origin"] for c in contacts})
    by_channel = []
    for origin in origins:
        channel_contacts = [c for c in contacts if c["origin"] == origin]
        channel_ids = {c["id"] for c in channel_contacts}
        won_contact_ids = {d["contact_id"] for d in won_deals if d["contact_id"] in channel_ids}
        by_channel.append({"origin": origin, "total": len(channel_contacts), "won": len(won_contact_ids)})

    loss_counts: dict[str, int] = {}
    for d in deals:
        if d["outcome"] == "perdido" and d.get("loss_reason"):
            loss_counts[d["loss_reason"]] = loss_counts.get(d["loss_reason"], 0) + 1
    loss_ranking = sorted(
        ({"reason": reason, "count": count} for reason, count in loss_counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "new_leads_month": new_leads_month,
        "in_negotiation_value": in_negotiation_value,
        "revenue_month": revenue_month,
        "revenue_prev_month": revenue_prev_month,
        "conversion_rate": conversion_rate,
        "net_profit_month": net_profit_month,
        "funnel_counts": funnel_counts,
        "by_channel": by_channel,
        "loss_ranking": loss_ranking,
    }
