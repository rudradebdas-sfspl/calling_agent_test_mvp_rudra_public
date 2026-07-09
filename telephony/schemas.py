"""
schemas.py
==========
Pydantic request/response models for the telephony API.
"""

from typing import Optional
from pydantic import BaseModel, Field


class SingleCallRequest(BaseModel):
    """Request body for initiating a single outbound call."""
    phone_number: str = Field(
        ...,
        description="Target phone number with country code, e.g. 919513886363 or +919513886363"
    )
    custom_field: Optional[str] = Field(None, description="Optional tag for CDR")
    name: Optional[str] = Field(None, description="Callee name for personalized greeting")
    gender: Optional[str] = Field(None, description="Callee gender: male/female/other")
    agent_id: Optional[int] = Field(None, description="Optional custom agent to handle the call")


class SingleCallResponse(BaseModel):
    success: bool
    message: str
    call_sid: Optional[str] = None
    call_status: Optional[str] = None
    log_id: Optional[int] = None


class BatchCallResponse(BaseModel):
    success: bool
    message: str
    batch_id: str
    total: int
    dispatched: int
    failed: int
    errors: list[dict] = []


class CallLogEntry(BaseModel):
    id: int
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    phone_number: str
    direction: str
    status: str
    call_sid: Optional[str]
    batch_id: Optional[str]
    created_at: str
    updated_at: Optional[str]
    duration: Optional[int]
    error_message: Optional[str]
    provider: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    callback_time: Optional[str] = None
    recording_url: Optional[str] = None
    recording_file_path: Optional[str] = None
    recording_sid: Optional[str] = None
    transcript_text: Optional[str] = None
    transcript_json: Optional[str] = None
    transcript_entries: list[dict] = []
    last_transcript_at: Optional[str] = None


class CallLogsResponse(BaseModel):
    logs: list[CallLogEntry]
    total: int


class CallStatsResponse(BaseModel):
    total_calls: int
    completed: int
    failed: int
    initiated: int
