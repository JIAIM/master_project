from langchain_core.prompts import ChatPromptTemplate

LANGUAGE_NAMES = {"uk": "Ukrainian", "ru": "Russian", "en": "English", "pl": "Polish"}

BLOOM_BY_DIFFICULTY = {
    "easy": "Remember/Understand: recall a key fact, definition or term explicitly stated in the context",
    "medium": "Understand/Apply: explain a relationship, classify an example, or apply a rule to a simple situation",
    "hard": "Analyze/Evaluate: compare concepts, infer a consequence, or identify correct multi-step reasoning; still fully grounded in the context",
}

TRANSFORM_INSTRUCTIONS = {
    "simplify": (
        "Make the question EASIER by one level: more direct wording, test a more explicitly stated fact, "
        "keep distractors plausible but more clearly distinguishable."
    ),
    "complicate": (
        "Make the question HARDER by one level: require reasoning or application instead of recall, "
        "make distractors closer to the correct answer, based on subtle misconceptions."
    ),
    "rephrase": "Rephrase the stem and options for clarity without changing the tested concept or difficulty.",
    "improve_distractors": (
        "Keep the stem and the correct answer. Replace weak distractors with more plausible ones "
        "based on typical student misconceptions."
    ),
    "regenerate": (
        "Discard this item entirely and write a completely NEW, different test item from the same CONTEXT: "
        "a different tested fact or concept, not a reword of the old one. Follow all item-writing rules from "
        "scratch, in particular: test the SUBJECT MATTER described in the CONTEXT, never the document itself "
        "(its author, title, structure or paragraph numbering)."
    ),
}


def type_rules(question_type: str, num_options: int, language: str) -> str:
    if question_type == "multiple_choice":
        return (
            f"multiple_choice: exactly {num_options} options, 2 or 3 of them correct, the rest distractors. "
            "The stem must make clear that several answers may be correct."
        )
    if question_type == "true_false":
        return (
            "true_false: the stem is a declarative statement. Exactly 2 options: the words for "
            f"'True' and 'False' in {language}, in that order. Exactly one is correct."
        )
    return f"single_choice: exactly {num_options} options, exactly ONE correct."


GENERATOR_SYSTEM = """You are an expert in educational assessment and test item writing.
You write high-quality multiple-choice test items strictly based on the provided CONTEXT from course materials.

Item-writing rules:
1. The correct answer must be fully supported by the CONTEXT. Never use facts that are not in the CONTEXT.
2. The stem must be self-contained and understandable without the CONTEXT. Never write "according to the text", "in the passage", etc.
2b. Test the SUBJECT MATTER the CONTEXT describes (the domain knowledge), as if examining the student on the
    topic. NEVER ask about the document/material itself: its author, title, who compiled it, which paragraph
    or section covers something, page/chapter numbers, or any other metadata about the source text. A student
    who has mastered the TOPIC but never saw this specific document must still be able to answer.
2c. If the CONTEXT looks like a reference list, bibliography, or a list of links/sources (URLs, citations,
    "recommended reading") rather than actual teaching content, do NOT write a question about which source
    covers what or which URL belongs to what tool/resource — that tests memorization of citations, not
    knowledge. Prefer picking a fact from whatever non-bibliographic content remains in the CONTEXT instead.
3. Avoid negative stems ("Which is NOT...") unless unavoidable; if used, the negation must be emphasized in CAPITALS.
4. Distractors must be plausible to a student who has not mastered the material: base each on a typical misconception, a common confusion of related terms, or a partially correct idea.
5. All options must be homogeneous: similar length, the same grammatical form and level of detail. The correct option must NOT be noticeably longer or more precise than the distractors.
6. Never use "all of the above", "none of the above" or their equivalents in any language.
7. Do not repeat distinctive words from the stem only in the correct option (no verbal clues).
8. evidence_quote must be copied VERBATIM from the CONTEXT.
9. Write the question, options and explanation in {language}."""

GENERATOR_HUMAN = """CONTEXT:
\"\"\"
{context}
\"\"\"

Target difficulty: {difficulty} — Bloom level: {bloom}
Question format: {type_rules}

Questions already in this test (do NOT duplicate their content or tested fact):
{existing}
{revision_block}
Write ONE test item."""

GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [("system", GENERATOR_SYSTEM), ("human", GENERATOR_HUMAN)]
)

SOLVER_SYSTEM = """You are a diligent student taking a test. Answer the question using ONLY the provided CONTEXT.
If the question allows several correct answers, choose all of them. Options are numbered from 1."""

SOLVER_HUMAN = """CONTEXT:
\"\"\"
{context}
\"\"\"

{question_block}"""

SOLVER_PROMPT = ChatPromptTemplate.from_messages(
    [("system", SOLVER_SYSTEM), ("human", SOLVER_HUMAN)]
)

CRITIC_SYSTEM = """You are a strict reviewer of test items for a university e-learning system.
Evaluate the item ONLY against the provided CONTEXT; your own background knowledge may be used only to detect factual errors.

Check:
- Grounding: is the keyed answer explicitly supported by the CONTEXT? Any invented or unsupported facts = hallucination.
- Correctness: is the keyed answer actually correct?
- Meta-question: does the item ask about the DOCUMENT itself (its author, title, who compiled it, which
  paragraph/section discusses something, page numbers) instead of the subject-matter knowledge it describes?
  Such an item is INVALID regardless of grounding — treat it as unambiguous=false and explain why in issues.
- Ambiguity: could any distractor be reasonably defended as correct? Is the stem vague?
- Distractors: are they plausible to a weak student, homogeneous in length and form, free of obvious absurdities?
- Clues: does the stem or option wording give away the answer?
- Difficulty: does the cognitive level match the requested difficulty?

Be strict: if in doubt, report the issue. Write issues and suggestions in {language}."""

CRITIC_HUMAN = """CONTEXT:
\"\"\"
{context}
\"\"\"

Requested difficulty: {difficulty} — {bloom}
Question type: {question_type}

ITEM UNDER REVIEW:
{question_block}
KEYED CORRECT OPTION(S): {keyed}
EXPLANATION: {explanation}
EVIDENCE QUOTE: {evidence_quote}
{solver_block}"""

CRITIC_PROMPT = ChatPromptTemplate.from_messages(
    [("system", CRITIC_SYSTEM), ("human", CRITIC_HUMAN)]
)
