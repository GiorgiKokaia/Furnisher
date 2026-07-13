"""Structured shapes the agent produces (docs/04)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StyleProfile(BaseModel):
    style_tags: list[str] = Field(default_factory=list)  # e.g. ["scandinavian", "minimal"]
    palette: list[str] = Field(default_factory=list)  # color names or hex
    materials: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    notes: str = ""


class ProposedItem(BaseModel):
    item_id: str  # MUST come from a search_catalog result (grounding rule)
    purpose: str  # short unique label: "bed", "left nightstand"
    hint: Literal["wall", "center", "free"] = "wall"
    anchor: str | None = None  # purpose of another item to place right next to


class RoomProposal(BaseModel):
    items: list[ProposedItem] = Field(default_factory=list)
    rationale: str = ""


class RoomOption(BaseModel):
    label: str = ""  # short: "Essentials", "Comfort", "Splurge"
    items: list[ProposedItem] = Field(default_factory=list)
    rationale: str = ""


class RoomOptions(BaseModel):
    options: list[RoomOption] = Field(default_factory=list)


class Intent(BaseModel):
    action: Literal["furnish_room", "set_budget", "clear_room", "question"]
    room_id: str | None = None  # exact id from the plan's room list
    budget: float | None = None
    note: str = ""  # extra constraints the user stated ("no wardrobe", "dark wood")
