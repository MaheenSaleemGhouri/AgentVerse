"""`RubricType.LLM_JUDGE` scoring — a second model call, graded against
a fixed reference answer and named criteria (CLAUDE.md §9: "LLM-as-
judge only with a fixed reference-anchored rubric", never a bare "does
this look good" prompt — `decision-log.md` #25's named drift risk).

Reserved for prompts no structural or keyword check can meaningfully
grade; `eval_scoring.py`'s deterministic scorers are always preferred
where they apply.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.entities import ChatMessage, ChatRequest
from agentverse_api.orchestration_service.domain.eval_scoring import ExampleScore
from agentverse_api.orchestration_service.domain.golden_dataset import LlmJudgeExpectation
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter

#: The one grading prompt every LLM-judge call uses — fixed, not
#: authored per golden example, so the rubric cannot drift example to
#: example (the exact failure mode `decision-log.md` #25 warns about).
#: Every criterion must be satisfied for a PASS; the judge states which
#: failed, giving the "failing eval results shown" acceptance criterion
#: something concrete to display.
_JUDGE_SYSTEM_PROMPT = (
    "You are grading one AI response against a reference answer and a fixed list of "
    "criteria. You do not grade style or phrasing — only whether the response satisfies "
    "each criterion, using the reference answer as the standard of what satisfying it "
    "means.\n\n"
    "Respond with exactly these fields, one per line:\n"
    "verdict: PASS or FAIL\n"
    "reason: one sentence citing the specific criterion that failed, or why all passed\n\n"
    "FAIL if the response contradicts the reference answer's substance, omits something "
    "a criterion requires, or states something the reference answer does not support. "
    "Minor wording differences are not a failure."
)

#: This judge call is a fixed, cheap classification task — deliberately
#: not the target model under test, mirroring `ai-architect`'s model-
#: routing table pattern (cheap/fast model for classification, never
#: the model whose *output* is what's being judged).
_JUDGE_MODEL = "gpt-4o-mini"


def _judge_user_turn(*, candidate_output: str, expectation: LlmJudgeExpectation) -> str:
    criteria = "\n".join(f"- {c}" for c in expectation.criteria)
    return (
        f"Reference answer:\n{expectation.reference_answer}\n\n"
        f"Criteria:\n{criteria}\n\n"
        f"Response to grade:\n{candidate_output}"
    )


async def score_llm_judge(
    *, adapter: ProviderAdapter, candidate_output: str, expectation: LlmJudgeExpectation
) -> ExampleScore:
    request = ChatRequest(
        model=_JUDGE_MODEL,
        messages=[
            ChatMessage(role="system", content=_JUDGE_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=_judge_user_turn(
                    candidate_output=candidate_output, expectation=expectation
                ),
            ),
        ],
        temperature=0.0,
    )
    result = await adapter.chat(request)

    lines = result.content.splitlines()
    verdict_line = next(
        (line for line in lines if line.strip().lower().startswith("verdict:")), ""
    )
    reason_line = next((line for line in lines if line.strip().lower().startswith("reason:")), "")
    passed = verdict_line.strip().lower().endswith("pass")
    reason = reason_line.split(":", 1)[1].strip() if ":" in reason_line else result.content.strip()
    return ExampleScore(passed=passed, reason=reason or "judge gave no reason")
