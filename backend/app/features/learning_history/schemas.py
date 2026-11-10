"""Response schemas for the learning history and unit ranking (API設計 3.6・3.7)."""

from datetime import datetime

from pydantic import BaseModel


class HistoryUnit(BaseModel):
    code: str
    name: str


class HistoryItem(BaseModel):
    id: str
    recorded_at: datetime
    unit: HistoryUnit
    score: int
    max_score: int


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    limit: int
    offset: int
    has_more: bool


class UnitRankingItem(BaseModel):
    rank: int
    unit: HistoryUnit
    average_score_rate: float
    record_count: int


class UnitRankingResponse(BaseModel):
    items: list[UnitRankingItem]
