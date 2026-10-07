"""Агент-Генератор: фрагменти матеріалу → структуроване тестове питання."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import Runnable

from app.services.generation.prompts import (
    BLOOM_BY_DIFFICULTY, GENERATOR_PROMPT, LANGUAGE_NAMES, type_rules,
)
from app.services.generation.schemas import LLMQuestion

MAX_EXISTING_IN_PROMPT = 25


@dataclass(frozen=True)
class GenerationSpec:
    difficulty: str       # easy | medium | hard
    question_type: str    # single_choice | multiple_choice | true_false
    language: str = "uk"
    target_answer: str | None = None  # true | false — для «правда/неправда»

    @property
    def num_options(self) -> int:
        return {"true_false": 2, "multiple_choice": 5}.get(self.question_type, 4)

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES.get(self.language, self.language)

    @property
    def bloom(self) -> str:
        return BLOOM_BY_DIFFICULTY[self.difficulty]


class QuestionGenerator:
    def __init__(self, llm) -> None:
        structured = llm.with_structured_output(LLMQuestion)
        self._chain: Runnable = (GENERATOR_PROMPT | structured).with_retry(
            stop_after_attempt=2, wait_exponential_jitter=True
        )

    async def generate(
        self,
        *,
        context: str,
        spec: GenerationSpec,
        existing_stems: list[str],
        previous: LLMQuestion | None = None,
        feedback: list[str] | None = None,
        instruction: str | None = None,
    ) -> LLMQuestion:
        existing = "\n".join(f"- {s}" for s in existing_stems[-MAX_EXISTING_IN_PROMPT:]) or "(none)"

        revision_block = ""
        if previous is not None:
            revision_block += f"\nPREVIOUS VERSION OF THE ITEM:\n{previous.model_dump_json(indent=2)}\n"
        if instruction:
            revision_block += f"\nTEACHER INSTRUCTION: {instruction}\n"
        if feedback:
            joined = "\n".join(f"- {f}" for f in feedback if f)
            revision_block += (
                f"\nA REVIEWER REJECTED THE PREVIOUS VERSION. Issues:\n{joined}\n"
                "Write an improved item that fixes ALL issues.\n"
            )

        result = await self._chain.ainvoke({
            "context": context,
            "language": spec.language_name,
            "difficulty": spec.difficulty,
            "bloom": spec.bloom,
            "type_rules": type_rules(spec.question_type, spec.num_options, spec.language_name, spec.target_answer),
            "existing": existing,
            "revision_block": revision_block,
        })
        if not isinstance(result, LLMQuestion):  
            result = LLMQuestion.model_validate(result)
        return result
