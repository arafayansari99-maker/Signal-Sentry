from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompetitorBase(BaseModel):
    name: str
    domain: str
    status: str = "active"
    crawl_cadence: str = "weekly"


class CompetitorCreate(CompetitorBase):
    pass


class CompetitorRead(CompetitorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class DiscoveryCandidate(BaseModel):
    url: str
    page_type: str


class ChangeItemSummary(BaseModel):
    category: str
    magnitude: str
    summary: str
    why_it_matters: str
    confidence: float
    status: str = "pending"
