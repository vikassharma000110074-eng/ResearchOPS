from typing import Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class HistoricalPoint(BaseModel):
    year: int = Field(ge=1900, le=2200)
    value: float = Field(gt=0, allow_inf_nan=False)


class ResearchRequest(BaseModel):
    question: str = Field(min_length=8, max_length=4000)
    geography: Optional[str] = Field(default=None, max_length=300)
    industry: Optional[str] = Field(default=None, max_length=300)
    max_tasks: int = Field(default=3, ge=3, le=5)

    # Kept for backward compatibility with older clients. v1.6 uses research_mode
    # to drive an adaptive multi-query web sweep instead of a fixed source count.
    sources_per_task: int = Field(default=8, ge=2, le=50)
    research_mode: Literal['Standard', 'Deep', 'Exhaustive'] = 'Standard'

    baseline_value: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    historical_data: list[HistoricalPoint] = Field(default_factory=list, max_length=200)
    forecast_years: int = Field(default=5, ge=1, le=5)
    include_decision_suggestion: bool = False
    decision_style: str = Field(default='Balanced', max_length=60)

    @field_validator('question')
    @classmethod
    def clear_question(cls, value):
        value = value.strip()
        if len(value) < 8: raise ValueError('Enter a clear research problem with at least eight characters.')
        return value

    @field_validator('historical_data')
    @classmethod
    def unique_years(cls, values):
        if len({x.year for x in values}) != len(values): raise ValueError('Historical data must contain only one value per year.')
        return values


class ResearchAccepted(BaseModel):
    research_id: str
    status: str


class JobStatus(BaseModel):
    research_id: str
    status: str
    stage: str
    progress: int
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    request: Optional[dict[str, Any]] = None
