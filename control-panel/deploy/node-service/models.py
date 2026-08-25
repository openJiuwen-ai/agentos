"""Pydantic models for vLLM Control API."""

from typing import Optional
from pydantic import BaseModel


class ApiResponse(BaseModel):
    """Standard API response."""
    success: bool
    message: str
    data: Optional[dict] = None
