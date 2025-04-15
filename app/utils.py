from sympy import simplify
from sympy.parsing.latex import parse_latex
from typing import Dict, Any

def is_expression_equal(user_input: str, correct_input: str) -> bool:
    try:
        user_expr = simplify(parse_latex(user_input))
        correct_expr = simplify(parse_latex(correct_input))
        return user_expr.equals(correct_expr)
    except Exception as e:
        print("Error in comparison:", e)
        return False

def check_answers(user_data: Dict[str, Any], correct_data: Dict[str, Any]) -> Dict[str, Any]:
    answers_1_35 = user_data['answers_1_35']
    answers_36_45 = user_data['answers_36_45']
    test = correct_data

    results_1_35 = {}
    results_36_45 = {}
    total_correct = 0

    for q, user_ans in answers_1_35.items():
        correct = test.answers_1_35[int(q)]
        is_correct = user_ans.upper() == correct.upper()
        if is_correct:
            total_correct += 1
        results_1_35[q] = {
            "is_correct": is_correct,
            "correct_answer": correct
        }

    for q, parts in answers_36_45.items():
        correct_parts = test.answers_36_45.get(q)
        if not correct_parts:
            continue

        results_36_45[q] = {}

        for part in ['a', 'b']:
            user_input = getattr(parts, part)
            correct_input = correct_parts.get(part)
            if correct_input is None:
                continue

            is_correct = is_expression_equal(user_input, correct_input)
            if is_correct:
                total_correct += 0.5

            results_36_45[q][part] = {
                "is_correct": is_correct,
                "correct_answer": correct_input
            }

    return {
        "results_1_35": results_1_35,
        "results_36_45": results_36_45,
        "total_correct": total_correct
    }