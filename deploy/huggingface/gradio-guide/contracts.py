"""Space adapter contract matching AI Chat/app/main.py; no model or DB imports."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Context(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifactId: int = Field(gt=0)
    artifactName: str = Field(max_length=1000)
    title: str = Field(max_length=1000)
    description: str = Field(max_length=24000)
    narrationText: str = Field(default='', max_length=24000)

    @model_validator(mode='after')
    def bound_source(self):
        if sum(len(v) for v in [self.artifactName, self.title, self.description, self.narrationText]) > 24000:
            raise ValueError('Source too long')
        return self


class Turn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(pattern='^(user|assistant)$')
    text: str = Field(min_length=1, max_length=4000)


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context: Context
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def validate_history(self):
        if not self.question.strip() or len(self.history) % 2 or any(
            t.role != ('user' if i % 2 == 0 else 'assistant') or not t.text.strip() for i, t in enumerate(self.history)
        ):
            raise ValueError('Invalid question/history')
        return self
