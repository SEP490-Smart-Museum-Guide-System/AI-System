from pydantic import BaseModel, ConfigDict, Field


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=12000, description="Approved narration text")
    language: str = Field(default="vi-VN", pattern="^vi(-VN)?$")
    speed: float = Field(default=1.0, ge=0.75, le=1.25)
