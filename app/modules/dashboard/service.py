from calendar import monthrange
from datetime import UTC, datetime

from app.core.supabase_client import get_service_client

STAGES = ["novo_lead", "em_atendimento", "negociacao", "fechamento", "pos_venda"]
MONTH_NAMES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _month_bounds(reference: datetime) -> tuple[str, str]:
    start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(reference.year, reference.month)[1]
    end = reference.replace(day=last_day, hour=23, minute=59, second=59)
    return start.isoformat(), end.isoformat()


def _prev_month_reference(reference: datetime) -> datetime:
    if reference.month == 1:
        return reference.replace(year=reference.year - 1, month=12)
    return reference.replace(month=reference.month - 1)


def _deal_net_profit(deal: dict) -> float:
    return (
        deal["value"]
        - (deal.get("supplier_value") or 0)
        - (deal.get("gift_value") or 0)
        - (deal.get("freight_value") or 0)
    )


def _add_months(reference: datetime, delta: int) -> datetime:
    month_index = reference.month - 1 + delta
    year = reference.year + month_index // 12
    month = month_index % 12 + 1
    return reference.replace(year=year, month=month)


def get_metrics(tenant_id: str) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC)
    month_start, month_end = _month_bounds(now)
    prev_start, prev_end = _month_bounds(_prev_month_reference(now))

    contacts = sb.table("contacts").select("*").eq("tenant_id", tenant_id).execute().data
    deals = sb.table("deals").select("*").eq("tenant_id", tenant_id).execute().data
    expenses = sb.table("expenses").select("*").eq("tenant_id", tenant_id).execute().data

    new_leads_month = sum(1 for c in contacts if month_start <= c["first_contact_at"] <= month_end)

    in_negotiation_value = sum(
        d["value"] for d in deals if d["outcome"] == "aberto" and d["stage"] in ("negociacao", "fechamento")
    )

    won_deals = [d for d in deals if d["outcome"] == "ganho"]
    revenue_month = sum(d["value"] for d in won_deals if month_start <= d["stage_changed_at"] <= month_end)
    revenue_prev_month = sum(d["value"] for d in won_deals if prev_start <= d["stage_changed_at"] <= prev_end)
    expenses_month = sum(e["value"] for e in expenses if month_start <= e["created_at"] <= month_end)
    # Lucro líquido de verdade da loja no mês: soma o lucro por negócio (venda
    # - custo de fornecedor - brindes - frete) e desconta os gastos gerais do
    # mês (aluguel, contas etc.) — antes disso o card só refletia custo por
    # venda, nunca o que a loja gasta pra existir.
    net_profit_month = (
        sum(_deal_net_profit(d) for d in won_deals if month_start <= d["stage_changed_at"] <= month_end)
        - expenses_month
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
        "expenses_month": expenses_month,
        "net_profit_month": net_profit_month,
        "funnel_counts": funnel_counts,
        "by_channel": by_channel,
        "loss_ranking": loss_ranking,
    }


def get_monthly_history(tenant_id: str, months: int) -> list[dict]:
    sb = get_service_client()
    now = datetime.now(UTC)
    contacts = sb.table("contacts").select("id, first_contact_at").eq("tenant_id", tenant_id).execute().data
    won_deals = (
        sb.table("deals")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("outcome", "ganho")
        .execute()
        .data
    )
    expenses = sb.table("expenses").select("value, created_at").eq("tenant_id", tenant_id).execute().data

    history = []
    for i in range(months - 1, -1, -1):
        ref = _add_months(now, -i)
        month_start, month_end = _month_bounds(ref)
        new_leads = sum(1 for c in contacts if month_start <= c["first_contact_at"] <= month_end)
        month_deals = [d for d in won_deals if month_start <= d["stage_changed_at"] <= month_end]
        month_expenses = sum(e["value"] for e in expenses if month_start <= e["created_at"] <= month_end)
        history.append(
            {
                "month": f"{MONTH_NAMES_PT[ref.month - 1]}/{ref.year}",
                "month_key": f"{ref.year}-{ref.month:02d}",
                "new_leads": new_leads,
                "revenue": sum(d["value"] for d in month_deals),
                "expenses": month_expenses,
                # Desconta os gastos gerais daquele mês — mesma lógica de
                # get_metrics, agora aplicada a cada mês do histórico.
                "net_profit": sum(_deal_net_profit(d) for d in month_deals) - month_expenses,
            }
        )
    return history


def get_monthly_detail(tenant_id: str, year: int, month: int) -> list[dict]:
    sb = get_service_client()
    ref = datetime(year, month, 1, tzinfo=UTC)
    month_start, month_end = _month_bounds(ref)

    deals = (
        sb.table("deals")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("outcome", "ganho")
        .gte("stage_changed_at", month_start)
        .lte("stage_changed_at", month_end)
        .execute()
        .data
    )
    if not deals:
        return []

    contact_ids = list({d["contact_id"] for d in deals})
    contacts = sb.table("contacts").select("id, name").in_("id", contact_ids).execute().data
    contact_names = {c["id"]: c["name"] for c in contacts}

    rows = [
        {
            "deal_id": d["id"],
            "contact_id": d["contact_id"],
            "contact_name": contact_names.get(d["contact_id"], "—"),
            "products": d["products"],
            "payment": d["payment"],
            "value": d["value"],
            "supplier_value": d.get("supplier_value") or 0,
            "gift_value": d.get("gift_value") or 0,
            "freight_value": d.get("freight_value") or 0,
            "net_profit": _deal_net_profit(d),
            "stage_changed_at": d["stage_changed_at"],
        }
        for d in deals
    ]
    rows.sort(key=lambda r: r["stage_changed_at"], reverse=True)
    return rows
