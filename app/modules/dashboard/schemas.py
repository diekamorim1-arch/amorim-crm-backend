from pydantic import BaseModel


class FunnelCount(BaseModel):
    stage: str
    count: int
    value: float


class ChannelStat(BaseModel):
    origin: str
    total: int
    won: int


class LossStat(BaseModel):
    reason: str
    count: int


class DashboardMetrics(BaseModel):
    new_leads_month: int
    in_negotiation_value: float
    revenue_month: float
    revenue_prev_month: float
    conversion_rate: float
    expenses_month: float
    net_profit_month: float
    funnel_counts: list[FunnelCount]
    by_channel: list[ChannelStat]
    loss_ranking: list[LossStat]


class MonthlyHistoryItem(BaseModel):
    month: str
    month_key: str
    new_leads: int
    revenue: float
    expenses: float
    net_profit: float


class MonthlyDealDetail(BaseModel):
    deal_id: str
    contact_id: str
    contact_name: str
    products: str
    payment: str
    value: float
    supplier_value: float
    gift_value: float
    freight_value: float
    net_profit: float
    stage_changed_at: str
