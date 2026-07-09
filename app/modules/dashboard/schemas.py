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
    net_profit_month: float
    funnel_counts: list[FunnelCount]
    by_channel: list[ChannelStat]
    loss_ranking: list[LossStat]
