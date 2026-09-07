from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LogoVariant = Literal["aprova-main", "custom-upload"]
ContentType = Literal["meta-ads", "news", "pinterest"]


class LogoPayload(BaseModel):
    variant: LogoVariant
    assetLabel: str = Field(..., description="Human-readable label for telemetry")
    data: str = Field(default="", description="Raw base64 without data: prefix")
    mimeType: str = Field(default="image/png", description="MIME type, e.g. image/png")


class GenerateRequest(BaseModel):
    aspect_ratio: str = Field(..., description="e.g. '4:5', '9:16', '1:1'")
    dimensions: str = Field(default="", description="Exact target pixels 'WxH', e.g. '1080x1350'. Falls back to aspect_ratio map when empty.")
    objective: str = Field(..., min_length=1, description="Campaign objective / news context / central idea")
    quantity: int = Field(..., ge=1, le=20, description="Number of creatives (1-20)")
    logo: LogoPayload
    content_type: ContentType = Field(default="meta-ads", description="Type of creative: meta-ads | news | pinterest")


class VariationContext(BaseModel):
    """Internal context built per creative variation before agent pipeline."""

    content_type: ContentType
    objetivo_campanha: str          # campaign objective / ideia central
    formato: str                    # "quadrado" | "vertical" | "horizontal"
    dimensoes: str                  # exact target px, e.g. "1080x1350"
    aspect_ratio: str
    variacao_numero: int
    total_variacoes: int
    logo_base64: str
    logo_mime_type: str
    research_brief: str = ""        # real, web-sourced facts shared across variations


class GeneratedImage(BaseModel):
    filename: str
    data: bytes
    mime_type: str
