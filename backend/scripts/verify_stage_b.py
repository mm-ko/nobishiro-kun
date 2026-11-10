"""Run synthetic scenarios: from backend, python scripts/verify_stage_b.py.

Set OPENROUTER_API_KEY and OPENROUTER_MODEL in the process environment yourself.
Failures include validated status/code/cause labels or exception class names.
Invalid Stage B responses also include a predefined reason label, never raw errors.
Use --review to inspect patterns/explanations for these synthetic cases only.
Credentials, answer text and raw model responses are never printed.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "ai_analysis"))

from stage_b_cases import CASES, UNITS, make_input  # noqa: E402

from app.features.ai_analysis.clients.openrouter import (  # noqa: E402
    OpenRouterClient,
    OpenRouterError,
)
from app.features.ai_analysis.service import (  # noqa: E402
    StageBInvalidResponseError,
    run_stage_b,
)

STAGE_B_INVALID_REASONS = {
    "Stage B output is not valid JSON.": "invalid_json",
    "Invalid Stage B unit schema.": "invalid_unit_schema",
    "Unit status and master code do not match.": "unit_master_mismatch",
    "Invalid Stage B pattern schema.": "invalid_pattern_schema",
    "Pattern must refer to an incorrect ID.": "invalid_question_reference",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review", action="store_true", help="Show synthetic analysis text"
    )
    args = parser.parse_args()
    failures = 0
    try:
        client = OpenRouterClient()
    except OpenRouterError as exc:
        print(f"FAIL configuration error={type(exc).__name__}")
        return 1
    try:
        for case in CASES:
            diagnostic = ""
            try:
                result = run_stage_b(make_input(case), UNITS, client)
                passed = (
                    result.unit_status == case[4]
                    and (result.unit.code if result.unit else None) == case[5]
                )
                if case[0] == "blank":
                    passed = passed and any(
                        p.cause_type == "blank" for p in result.patterns or []
                    )
                if case[0] == "blank_grouping":
                    passed = (
                        passed
                        and result.patterns is not None
                        and len(result.patterns) == 1
                        and result.patterns[0].cause_type == "blank"
                        and result.patterns[0].pattern == "判定困難"
                        and result.patterns[0].question_numbers == ["1:1(1)", "2:1(1)"]
                    )
                if case[0] == "carry":
                    passed = (
                        passed
                        and bool(result.patterns)
                        and all(p.cause_type == "undetermined" for p in result.patterns)
                        and any(
                            "1:1(1)" in p.question_numbers
                            and any(
                                word in p.pattern
                                for word in ("繰り上が", "繰上", "くり上が", "くりあが")
                            )
                            and any(
                                word in p.pattern
                                for word in (
                                    "漏れ",
                                    "忘",
                                    "反映",
                                    "加え",
                                    "足し",
                                    "加算",
                                )
                            )
                            for p in result.patterns
                        )
                        and all(
                            any(
                                word in p.explanation
                                for word in (
                                    "判定困難",
                                    "判断できません",
                                    "断定できません",
                                    "区別できません",
                                )
                            )
                            for p in result.patterns
                        )
                    )
                if case[0] == "remainder":
                    passed = (
                        passed
                        and bool(result.patterns)
                        and all(p.cause_type == "undetermined" for p in result.patterns)
                        and any(
                            "1:1(1)" in p.question_numbers
                            and any(word in p.pattern for word in ("あまり", "余り"))
                            and any(
                                word in p.pattern
                                for word in ("誤り", "ミス", "間違", "まちが")
                            )
                            for p in result.patterns
                        )
                        and all("判定困難" in p.explanation for p in result.patterns)
                    )
                if case[0] == "transcription":
                    passed = (
                        passed
                        and bool(result.patterns)
                        and all(
                            p.question_numbers == ["1:1(1)"]
                            and p.cause_type == "careless_mistake"
                            and any(
                                word in p.pattern
                                for word in ("書き写", "書写", "転記", "写し間違")
                            )
                            and any(
                                word in p.pattern
                                for word in ("誤り", "ミス", "間違", "まちが")
                            )
                            and "ケアレスミスの可能性" in p.explanation
                            and "原因は断定できません。" in p.explanation
                            and not any(
                                word in p.explanation
                                for word in (
                                    "ケアレスミスです",
                                    "理解不足",
                                    "理解でき",
                                    "原因はケアレスミス",
                                )
                            )
                            for p in result.patterns
                        )
                    )
                if args.review:
                    print(
                        f"  review case={case[0]} "
                        f"unit_status={result.unit_status.value}"
                    )
                    for item in result.patterns or []:
                        print(
                            f"  questions={item.question_numbers} "
                            f"cause={item.cause_type.value}"
                        )
                        print(f"  pattern={item.pattern}")
                        print(f"  explanation={item.explanation}")
                if not passed:
                    causes = [p.cause_type.value for p in result.patterns or []]
                    diagnostic = (
                        f"unit_status={result.unit_status.value} "
                        f"unit_code={result.unit.code if result.unit else None} "
                        f"causes={causes} "
                        f"expected_unit_status={case[4]} expected_unit_code={case[5]}"
                    )
            except (OpenRouterError, StageBInvalidResponseError) as exc:
                passed = False
                diagnostic = f"error={type(exc).__name__}"
                if isinstance(exc, StageBInvalidResponseError):
                    reason = STAGE_B_INVALID_REASONS.get(
                        str(exc), "unknown_invalid_response"
                    )
                    diagnostic += f" reason={reason}"
                    if exc.validation_issues:
                        diagnostic += (
                            f" validation_issues={list(exc.validation_issues)}"
                        )
            print(f"{case[0]}: {'PASS' if passed else 'FAIL'}")
            if diagnostic:
                print(f"  {diagnostic}")
            failures += not passed
    finally:
        client.close()
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
