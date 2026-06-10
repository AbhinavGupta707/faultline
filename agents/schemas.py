"""Pydantic models mirroring contracts/schemas/faultline.schema.json (FROZEN).

Every agent emission is built as one of these models, so payloads validate at the
boundary instead of via prompt hope (impl plan §6). Serialization rule: dump with
``exclude_none=True, by_alias=True`` — optional fields are *omitted*, never null,
matching the contract's strict required / ignore-unknown-extras convention.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "earthquake", "flood", "storm", "hurricane", "wildfire", "industrial_accident",
    "recall", "strike", "port_disruption", "drought", "frost", "geopolitical", "other",
]
Capacity = Literal["low", "medium", "high"]
ExposureStatus = Literal["at_risk", "watch", "secured"]
DecisionKind = Literal[
    "triage", "trace", "assess", "approval", "resource", "negotiate", "verify",
    "brief", "enrich", "other",
]
MatchMethod = Literal["hybrid_bm25_elser", "semantic", "geo", "exact"]


class ContractModel(BaseModel):
    """Base: tolerate unknown extra fields (forward compatibility, per contract)."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def wire(self) -> dict[str, Any]:
        """Contract-shaped dict for the WS / Elastic boundary."""
        return self.model_dump(mode="json", exclude_none=True, by_alias=True)


class GeoPoint(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class WorldEvent(ContractModel):
    id: str
    source: str
    title: str
    summary: Optional[str] = None
    event_type: EventType
    location: GeoPoint
    place_name: str
    region: str
    severity_raw: float = Field(ge=0, le=1)
    published_at: str
    url: Optional[str] = None
    simulated: bool


class Supplier(ContractModel):
    supplier_id: str
    name: str
    tier: int = Field(ge=1, le=4)
    location: GeoPoint
    country: str
    region: str
    components: list[str]
    alternate_for: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    lead_time_days: int = Field(ge=0)
    expedited_lead_time_days: Optional[int] = Field(default=None, ge=0)
    capacity: Capacity
    profile_semantic: Optional[str] = None


class RelevantEvent(ContractModel):
    event_id: str
    title: str
    source: str
    event_type: EventType
    severity_raw: float = Field(ge=0, le=1)
    location: GeoPoint
    place_name: str
    published_at: str
    url: Optional[str] = None
    simulated: bool
    why_relevant: str
    supplier_hints: list[str] = Field(default_factory=list)


class TimeWindow(ContractModel):
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None


class RelevantEventsPayload(ContractModel):
    """agent.emit kind=relevant_events (Watcher)."""
    events: list[RelevantEvent]
    considered_count: Optional[int] = None
    window: Optional[TimeWindow] = None


class ChainNode(ContractModel):
    supplier_id: str
    name: str
    tier: int = Field(ge=1, le=4)
    role: Optional[str] = None
    location: Optional[GeoPoint] = None
    country: Optional[str] = None


class PathMatch(ContractModel):
    score: float = Field(ge=0, le=1)
    method: MatchMethod
    rationale: Optional[str] = None


class ExposurePath(ContractModel):
    path_id: str
    event_id: str
    supplier_chain: list[ChainNode] = Field(min_length=1)
    component_id: str
    component_name: str
    product_id: str
    product_name: str
    hops: int = Field(ge=1)
    match: PathMatch


class ExposurePathsPayload(ContractModel):
    """agent.emit kind=exposure_paths (Tracer)."""
    event_id: str
    paths: list[ExposurePath]


class Exposure(ContractModel):
    exposure_id: str
    rank: int = Field(ge=1)
    product_id: str
    product_name: str
    component_id: str
    root_cause_event_id: str
    chokepoint_supplier_id: str
    days_of_cover: float = Field(ge=0)
    est_disruption_days: float = Field(ge=0)
    dollars_at_risk_usd: float = Field(ge=0)
    monthly_revenue_usd: Optional[float] = Field(default=None, ge=0)
    severity: float = Field(ge=0, le=1)
    status: ExposureStatus
    rationale: str
    evidence_event_ids: list[str]
    path_ids: list[str]
    simulated: Optional[bool] = None


class RankedExposuresPayload(ContractModel):
    """agent.emit kind=ranked_exposures (Assessor)."""
    exposures: list[Exposure]
    enriched: Optional[bool] = None


class Alternate(ContractModel):
    supplier_id: str
    name: str
    tier: Optional[int] = None
    location: GeoPoint
    country: str
    lead_time_days: int = Field(ge=0)
    expedited_lead_time_days: Optional[int] = Field(default=None, ge=0)
    capacity: Capacity
    certifications: list[str] = Field(default_factory=list)
    match_score: float = Field(ge=0, le=1)
    est_unit_cost_usd: Optional[float] = Field(default=None, ge=0)
    rationale: Optional[str] = None


class AlternatesPayload(ContractModel):
    """agent.emit kind=alternates (Resourcer)."""
    exposure_id: str
    component_id: str
    alternates: list[Alternate]
    recommended_supplier_id: str


class DraftPOPayload(ContractModel):
    """agent.emit kind=draft_po (Resourcer) AND the po_generator input doc."""
    po_id: str
    run_id: Optional[str] = None
    exposure_id: str
    supplier_id: str
    supplier_name: str
    component_id: str
    component_name: str
    quantity: float = Field(gt=0)
    unit: str
    unit_price_usd: float = Field(gt=0)
    total_usd: float = Field(gt=0)
    currency: Literal["USD"] = "USD"
    incoterms: Optional[str] = None
    ship_mode: Optional[Literal["air", "sea", "road", "rail", "split"]] = None
    need_by_date: str
    lead_time_days: int = Field(ge=0)
    contingent: bool
    status: Literal["draft", "approved", "sent", "cancelled"]
    pdf_gcs_uri: Optional[str] = None
    notes: Optional[str] = None
    buyer: Optional[str] = None


class CallSummary(ContractModel):
    agreed: bool
    lead_time_days: Optional[int] = None
    expedited_lead_time_days: Optional[int] = None
    quantity: Optional[float] = None
    unit_price_usd: Optional[float] = None
    notes: Optional[str] = None


class CallEventPayload(ContractModel):
    """agent.emit kind=call_event (Negotiator / voice_gateway)."""
    call_id: str
    event: Literal["status", "transcript", "summary"]
    status: Optional[Literal["initiating", "ringing", "connected", "ended", "failed"]] = None
    speaker: Optional[Literal["faultline_agent", "supplier"]] = None
    text: Optional[str] = None
    is_final: Optional[bool] = None
    summary: Optional[CallSummary] = None


class ResidualRisk(ContractModel):
    level: Literal["low", "medium", "high"]
    factors: list[str]


class StatusChange(ContractModel):
    from_: ExposureStatus = Field(alias="from")
    to: ExposureStatus


class VerifyResultPayload(ContractModel):
    """agent.emit kind=verify_result (Verifier)."""
    exposure_id: str
    product_id: str
    gap_closed: bool
    days_of_cover: float
    alternate_lead_time_days: float
    margin_days: float
    residual_risk: ResidualRisk
    status_change: Optional[StatusChange] = None
    summary: str
    evidence_event_ids: list[str]


class DecisionRelated(ContractModel):
    product_ids: Optional[list[str]] = None
    supplier_ids: Optional[list[str]] = None
    component_ids: Optional[list[str]] = None
    exposure_ids: Optional[list[str]] = None
    path_ids: Optional[list[str]] = None
    approval_id: Optional[str] = None
    po_id: Optional[str] = None
    call_id: Optional[str] = None
    report_id: Optional[str] = None


class Decision(ContractModel):
    """`decision-log` doc AND the payload of ws decision.logged."""
    decision_id: str
    run_id: str
    ts: str
    agent: str
    kind: DecisionKind
    summary: str
    detail: Optional[str] = None
    evidence_event_ids: list[str]
    simulated: Optional[bool] = None
    related: Optional[DecisionRelated] = None


class PlanStep(ContractModel):
    id: str
    label: str
    status: Literal["pending", "active", "done", "error", "skipped"]


class ApprovalContext(ContractModel):
    exposure_ids: Optional[list[str]] = None
    product_ids: Optional[list[str]] = None
    component_id: Optional[str] = None
    recommended_supplier_id: Optional[str] = None
    po_id: Optional[str] = None
    dollars_at_risk_total_usd: Optional[float] = None
    evidence_event_ids: Optional[list[str]] = None


class ApprovalRequestPayload(ContractModel):
    approval_id: str
    action_kind: Literal["resource_alternate", "send_po", "negotiation_call", "other"]
    summary: str
    requested_by: Optional[str] = None
    context: ApprovalContext
    expires_at: Optional[str] = None


class WhatifScenario(ContractModel):
    scenario_id: Optional[str] = None
    preset: Optional[str] = None
    title: Optional[str] = None
    event_type: EventType
    location: GeoPoint
    place_name: Optional[str] = None
    duration_days: float = Field(gt=0)
    magnitude: float = Field(ge=0, le=1)
