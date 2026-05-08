from typing import Literal
from pydantic import BaseModel


class TraceStep(BaseModel):
    tool: str
    input: dict
    output: str


class StreamEvent(BaseModel):
    type: Literal["tool_start", "tool_end", "content_delta", "done", "error"]
    content: str = ""
    trace: list[TraceStep] = []
