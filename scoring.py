"""Scoring and statistics.

Main score of a model on a problem set
    N = number of problems in the set
    n = number of samples per problem (the largest sample count recorded for
        any problem of the set, so a missing sample counts as wrong)
    c = number of correct samples over the whole set
    score = 100 * c / (n * N)

Solved count: problems answered correctly at least once in the n samples.
"""
import re
from collections import defaultdict


def compute(sets, problems, models, samples):
    """Return a nested dict with every statistic the pages need."""
    # (model_id, problem_id) -> [correct, total]
    cell = defaultdict(lambda: [0, 0])
    for s in samples:
        c = cell[(s["model_id"], s["problem_id"])]
        c[0] += s["correct"]
        c[1] += 1

    probs_by_set = defaultdict(list)
    for p in problems:
        probs_by_set[p["set_id"]].append(p)

    # ---- model x set
    model_set = {}
    for m in models:
        for st in sets:
            ps = probs_by_set[st["id"]]
            N = len(ps)
            counts = [cell.get((m["id"], p["id"]), [0, 0]) for p in ps]
            n = max((k for _, k in counts), default=0)
            if N == 0 or n == 0:
                continue
            c = sum(ci for ci, _ in counts)
            model_set[(m["id"], st["id"])] = {
                "c": c, "n": n, "N": N,
                "score": 100.0 * c / (n * N),
                "solved": sum(1 for ci, _ in counts if ci > 0),
            }

    # ---- per problem
    problem = {}
    for p in problems:
        tot_c = tot_k = solved_by = evaluated_by = 0
        per_model = {}
        for m in models:
            ci, k = cell.get((m["id"], p["id"]), (0, 0))
            if k == 0:
                continue
            per_model[m["id"]] = {"c": ci, "k": k}
            tot_c += ci
            tot_k += k
            evaluated_by += 1
            solved_by += ci > 0
        rate = tot_c / tot_k if tot_k else None
        problem[p["id"]] = {
            "pass_rate": rate,
            "difficulty": None if rate is None else 1 - rate,
            "solved_by": solved_by,
            "evaluated_by": evaluated_by,
            "per_model": per_model,
        }

    # ---- per set
    set_stats = {}
    for st in sets:
        scores = [model_set[(m["id"], st["id"])]["score"]
                  for m in models if (m["id"], st["id"]) in model_set]
        best = max(
            ((model_set[(m["id"], st["id"])]["score"], m["name"])
             for m in models if (m["id"], st["id"]) in model_set),
            default=None,
        )
        mean = sum(scores) / len(scores) if scores else None
        set_stats[st["id"]] = {
            "mean_score": mean,
            "difficulty": None if mean is None else 1 - mean / 100,
            "evaluated_by": len(scores),
            "best": best,
            "N": len(probs_by_set[st["id"]]),
        }

    # ---- per model (overall = mean of set scores over the sets it was run on)
    model_stats = {}
    for m in models:
        rows = [model_set[(m["id"], st["id"])] for st in sets if (m["id"], st["id"]) in model_set]
        model_stats[m["id"]] = {
            "overall": sum(r["score"] for r in rows) / len(rows) if rows else None,
            "sets_run": len(rows),
            "solved": sum(r["solved"] for r in rows),
            "attempted": sum(r["N"] for r in rows),
            "samples": sum(r["n"] * r["N"] for r in rows),
            "correct": sum(r["c"] for r in rows),
        }

    return {
        "model_set": model_set,
        "problem": problem,
        "set": set_stats,
        "model": model_stats,
    }


# ---------------------------------------------------------------- answers

def extract_boxed(text):
    """Content of the last \\boxed{...} (or \\fbox{...}) in `text`, or None."""
    starts = [m.end() for m in re.finditer(r"\\(?:boxed|fbox)\s*\{", text)]
    if not starts:
        return None
    i = starts[-1]
    depth = 1
    j = i
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j].strip()
        j += 1
    return None


_STRIP = [r"\left", r"\right", r"\,", r"\!", r"\;", r"\:", r"\ ", r"\displaystyle", "$"]


def normalize(ans):
    s = (ans or "").strip()
    for tok in _STRIP:
        s = s.replace(tok, "")
    s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    s = re.sub(r"\\text\{\s*([^{}]*?)\s*\}", r"\1", s)
    s = re.sub(r"\s+", "", s)
    return s.rstrip(".")


def same_answer(given, reference):
    """Cheap automatic check. Admins can always override by hand."""
    a, b = normalize(given), normalize(reference)
    if not a:
        return False
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(b)))
    except ValueError:
        return False
