"""Pydantic-схеми структурованих відповідей LLM-агентів."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMOption(BaseModel):
    text: str = Field(description="Option text")
    is_correct: bool = Field(description="True if this option is a correct answer")
    rationale: str = Field(
        description=(
            "For the correct option: why it is correct. For a distractor: which specific "
            "misconception or typical student error it targets"
        )
    )


class LLMQuestion(BaseModel):
    question: str = Field(description="Self-contained question stem")
    options: list[LLMOption] = Field(description="Answer options")
    explanation: str = Field(description="Short explanation of the correct answer for students")
    evidence_quote: str = Field(
        description="Verbatim quote (max ~40 words) copied from the CONTEXT that proves the answer"
    )
    bloom_level: str = Field(description="Bloom's taxonomy level targeted by the question")


class SolverAnswer(BaseModel):
    chosen_options: list[int] = Field(description="1-based numbers of the option(s) you chose")
    confidence: float = Field(ge=0, le=1, description="Confidence from 0 to 1")
    reasoning: str = Field(description="One or two sentences of reasoning")


class CriticReport(BaseModel):
    grounding_score: float = Field(
        ge=0, le=1,
        description="How fully the keyed answer is supported by the CONTEXT (1 = explicitly stated)",
    )
    key_is_correct: bool = Field(description="The keyed correct answer(s) are actually correct")
    unambiguous: bool = Field(
        description="No distractor can be reasonably defended as correct; exactly the keyed set is right"
    )
    distractor_quality: float = Field(
        ge=0, le=1,
        description="Plausibility and homogeneity of distractors (1 = all plausible to a weak student)",
    )
    clarity: float = Field(ge=0, le=1, description="Stem clarity, grammar, no hints to the answer")
    difficulty_match: bool = Field(description="Cognitive level matches the requested difficulty")
    issues: list[str] = Field(default_factory=list, description="Concrete problems found")
    suggestions: str = Field(default="", description="How to fix the problems")
