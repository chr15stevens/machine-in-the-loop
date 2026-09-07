from pydantic import BaseModel, Field
from datetime import datetime


class RequestIn(BaseModel):
    """What the controller sends."""

    text: str = Field(min_length=1, max_length=500, description="The instruction, imperative and unambiguous.")
    note: str | None = Field(default=None, max_length=1000, description="Optional context the human may want.")


class Request(BaseModel):
    """What the human sees, and what the controller reads back."""

    id: int
    text: str
    note: str | None = None
    issued_at: datetime
    completed_at: datetime | None = None
    # Latency is the controller's only sensor, so it is a field rather than
    # something every client has to subtract for itself.
    elapsed_seconds: float | None = None

    @property
    def is_open(self) -> bool:
        return self.completed_at is None


class Completions(BaseModel):
    """The answer to a long-poll: what closed, and where to resume from."""

    cursor: int = Field(description="Pass this back as `since` on the next call.")
    completed: list[Request] = Field(description="Empty if the wait timed out.")