"""Hermes Print Automation - Data Models & Schemas.

Contains Pydantic models for WhatsApp webhooks, PDF analysis results,
LLM structured decisions, print job executions, and session states.
"""

from enum import Enum
from typing import List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class HermesAction(str, Enum):
    """Actions that Hermes AI agent can decide."""
    NEW_DOCUMENT_SUMMARY = "NEW_DOCUMENT_SUMMARY"
    CONFIRM_PRINT = "CONFIRM_PRINT"
    REVISE_PRINT_SETTINGS = "REVISE_PRINT_SETTINGS"
    REVISE_CONTENT_ADMIN = "REVISE_CONTENT_ADMIN"
    CHAT = "CHAT"
    CANCEL_PRINT = "CANCEL_PRINT"
    REQUEST_PDF = "REQUEST_PDF"


class SessionStatus(str, Enum):
    """Life-cycle status of a customer print session."""
    IDLE = "IDLE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    PRINTING = "PRINTING"
    PRINTED = "PRINTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    ADMIN_HANDOVER = "ADMIN_HANDOVER"
    CANCELLED = "CANCELLED"


class WhatsAppWebhookPayload(BaseModel):
    """Payload received from local Baileys WhatsApp Gateway."""
    sender: str = Field(..., description="Sender WhatsApp phone number")
    message: Optional[str] = Field(default="", description="Text message content")
    url: Optional[str] = Field(default=None, description="URL of attached media/file if any")
    filename: Optional[str] = Field(default=None, description="Original filename of attachment")
    filetype: Optional[str] = Field(default=None, description="File type e.g. document/image")
    name: Optional[str] = Field(default="", description="Sender profile name")
    local_file_path: Optional[str] = Field(default=None, description="Local path to downloaded attachment file")
    source: Optional[str] = Field(default="baileys", description="Gateway source")


class PDFAnalysisResult(BaseModel):
    """Detailed structural & visual analysis of a PDF file."""
    file_path: str
    original_filename: str
    total_pages: int
    color_pages_count: int
    bw_pages_count: int
    color_pages_list: List[int] = Field(default_factory=list)
    bw_pages_list: List[int] = Field(default_factory=list)
    color_low_pages: List[int] = Field(default_factory=list, description="Halaman warna < 50% (Rp 2.000)")
    color_high_pages: List[int] = Field(default_factory=list, description="Halaman warna >= 50% (Rp 2.500)")
    color_full_pages: List[int] = Field(default_factory=list, description="Halaman full warna (Rp 3.000)")
    color_low_count: int = 0
    color_high_count: int = 0
    color_full_count: int = 0
    paper_size: str
    dimensions_mm: str
    orientation: str
    text_excerpt: str
    is_color_document: bool
    estimated_price: int = 0


class HermesDecision(BaseModel):
    """Deterministic structured output schema produced by Hermes LLM."""
    model_config = ConfigDict(populate_by_name=True)

    action: HermesAction = Field(
        ...,
        validation_alias=AliasChoices("action", "intent", "decision"),
        description="The classified user intent and system action to take."
    )
    reply_message: str = Field(
        ...,
        validation_alias=AliasChoices("reply_message", "response", "message", "reply", "text"),
        description="Polite, WhatsApp-formatted response to send to the customer with emojis."
    )
    document_summary: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("document_summary", "summary", "overview"),
        description="Concise 1-3 sentence summary of the document contents (for NEW_DOCUMENT_SUMMARY)."
    )
    updated_copies: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("updated_copies", "copies", "count", "num_copies"),
        description="Updated number of copies if the customer requested a change."
    )
    updated_color_mode: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("updated_color_mode", "color_mode", "mode"),
        description="Updated color mode ('bw', 'color', 'auto') if customer requested a change."
    )
    updated_page_range: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("updated_page_range", "page_range", "pages"),
        description="Updated page range (e.g. '1-5', 'all', '1,3,5') if requested."
    )
    revision_notes_for_admin: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("revision_notes_for_admin", "revision_notes", "notes"),
        description="Notes detailing the customer's design/content change requests for manual admin handover."
    )
    reasoning: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("reasoning", "reason", "thought", "rationale"),
        description="Internal chain of thought explaining the classification decision."
    )


class SessionData(BaseModel):
    """In-memory and SQLite persistent state representation of a user session."""
    phone_number: str
    customer_name: str = ""
    current_file_path: Optional[str] = None
    original_filename: Optional[str] = None
    file_url: Optional[str] = None
    page_count: int = 0
    color_pages_count: int = 0
    bw_pages_count: int = 0
    color_low_pages_count: int = 0
    color_high_pages_count: int = 0
    color_full_pages_count: int = 0
    paper_size: str = "A4"
    orientation: str = "Potret"
    document_summary: str = ""
    copies: int = 1
    color_mode: str = "auto"  # 'auto', 'bw', 'color'
    page_range: str = "all"
    estimated_price: int = 0
    session_status: SessionStatus = SessionStatus.IDLE
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PrintJobResult(BaseModel):
    """Output summary of a physical print spooler execution."""
    success: bool
    command_executed: str
    printer_used: str
    copies: int
    color_mode: str
    pages: str
    error_message: Optional[str] = None
    is_simulated: bool = False
