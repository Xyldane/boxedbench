"""\\boxed{} - a small benchmark site for LLMs on hand-made problems.

Run:  python app.py            (serves on http://localhost:5000)
Env:  BOXED_ADMIN_PASSWORD     admin password (admin area is disabled without it)
      BOXED_SECRET_KEY         session signing key (random per start if unset)
      BOXED_DB                 path of the SQLite file (default ./boxed.db)
      BOXED_PORT               port (default 5000)
"""
import functools
import hmac
import json
import os
import posixpath
import secrets


def _load_dotenv():
    """Minimal .env support: KEY=VALUE lines, existing env vars win."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


_load_dotenv()

from flask import (Flask, Response, abort, flash, redirect, render_template,  # noqa: E402
                   request, session, url_for)

import db  # noqa: E402
import scoring  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("BOXED_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.teardown_appcontext(db.close_db)
db.init_db()

SUBJECTS = ["math", "physics", "chemistry", "biology", "python", "logic", "other"]


def load_all():
    d = db.get_db()
    sets = db.all_sets(d)
    problems = db.all_problems(d)
    models = db.all_models(d)
    stats = scoring.compute(sets, problems, models, db.all_samples(d))
    return sets, problems, models, stats


@app.template_filter("pct")
def pct(value, digits=1):
    return "–" if value is None else f"{value:.{digits}f}%"


@app.template_filter("num")
def num(value, digits=2):
    return "–" if value is None else f"{value:.{digits}f}"


@app.context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {"is_admin": session.get("admin", False), "csrf_token": session["csrf"],
            "subjects": SUBJECTS, "static_build": app.config.get("STATIC_BUILD", False)}


# ================================================================ static build
# build.py renders the public pages to plain files for GitHub Pages. In that
# mode every link is a relative path (set/1, ../static/style.css), so the site
# works under any sub-path or a custom domain. Page links drop ".html" because
# GitHub Pages serves set/1.html at set/1.

def page_file(path):
    """URL path of a public page -> its file in the static build."""
    if path == "/":
        return "index.html"
    path = path.lstrip("/")
    return path if path.startswith("static/") else path + ".html"


def link(endpoint, **values):
    url = url_for(endpoint, **values)
    if not app.config.get("STATIC_BUILD"):
        return url
    here = posixpath.dirname(page_file(request.path)) or "."
    rel = posixpath.relpath(page_file(url), here)
    if rel == "index.html":
        return "./"
    if rel.endswith("/index.html"):
        return rel[:-len("index.html")]
    return rel[:-len(".html")] if rel.endswith(".html") else rel


app.jinja_env.globals["url_for"] = link


# ================================================================ public pages

@app.route("/")
def index():
    sets, problems, models, stats = load_all()
    previews = {}
    for p in problems:
        previews.setdefault(p["set_id"], [])
        if len(previews[p["set_id"]]) < 2:
            previews[p["set_id"]].append(p)
    return render_template("index.html", sets=sets, previews=previews, stats=stats,
                           n_models=len(models), n_problems=len(problems))


@app.route("/set/<int:set_id>")
def set_page(set_id):
    d = db.get_db()
    st = db.get_set(d, set_id) or abort(404)
    sets, problems, models, stats = load_all()
    problems = db.set_problems(d, set_id)
    ranked = sorted(
        (m for m in models if (m["id"], set_id) in stats["model_set"]),
        key=lambda m: -stats["model_set"][(m["id"], set_id)]["score"],
    )
    return render_template("set.html", st=st, problems=problems, models=ranked, stats=stats)


@app.route("/problem/<int:problem_id>")
def problem_page(problem_id):
    d = db.get_db()
    p = db.get_problem(d, problem_id) or abort(404)
    st = db.get_set(d, p["set_id"])
    siblings = db.set_problems(d, p["set_id"])
    idx = [s["id"] for s in siblings].index(p["id"])
    _, _, models, stats = load_all()
    by_model = {}
    for s in db.problem_samples(d, problem_id):
        by_model.setdefault(s["model_id"], []).append(s)
    rows = [(m, by_model[m["id"]]) for m in models if m["id"] in by_model]
    rows.sort(key=lambda r: (-sum(s["correct"] for s in r[1]) / len(r[1]), r[0]["name"]))
    return render_template(
        "problem.html", p=p, st=st, idx=idx, rows=rows, pstats=stats["problem"][p["id"]],
        prev=siblings[idx - 1] if idx > 0 else None,
        next=siblings[idx + 1] if idx + 1 < len(siblings) else None,
    )


@app.route("/leaderboard")
def leaderboard():
    sets, problems, models, stats = load_all()
    ranked = sorted(
        models,
        key=lambda m: (stats["model"][m["id"]]["overall"] is None,
                       -(stats["model"][m["id"]]["overall"] or 0), m["name"]),
    )
    return render_template("leaderboard.html", sets=sets, models=ranked, stats=stats)


@app.route("/stats")
def stats_page():
    sets, problems, models, stats = load_all()
    return render_template("stats.html", diagram=build_diagram(sets, problems, models, stats),
                           sets=sets)


def build_diagram(sets, problems, models, stats):
    """Data for the commutative-diagram view: nodes on the left (models) point
    at nodes on the right (problem sets or problems); arrows carry scores."""
    ms, ps = stats["model_set"], stats["problem"]
    model_nodes = []
    for m in models:
        s = stats["model"][m["id"]]
        model_nodes.append({
            "id": m["id"], "label": m["name"],
            "sub": " · ".join(x for x in [m["params"], pct(s["overall"])] if x),
            "value": None if s["overall"] is None else s["overall"] / 100,
            "info": [
                ("Parameters", m["params"] or "–"), ("Family", m["family"] or "–"),
                ("Overall score", pct(s["overall"])),
                ("Problems solved", f'{s["solved"]} / {s["attempted"]}'),
                ("Correct samples", f'{s["correct"]} / {s["samples"]}'),
                ("Sets run", f'{s["sets_run"]} / {len(sets)}'),
            ],
        })

    set_nodes, set_edges = [], []
    for j, st in enumerate(sets):
        s = stats["set"][st["id"]]
        set_nodes.append({
            "id": st["id"], "label": st["title"], "url": link("set_page", set_id=st["id"]),
            "sub": f'{st["subject"]} · N={s["N"]} · diff {num(s["difficulty"])}',
            "value": s["difficulty"],
            "info": [
                ("Subject", st["subject"]), ("Problems", s["N"]),
                ("Difficulty", num(s["difficulty"]) + "  (1 − mean score)"),
                ("Mean score", pct(s["mean_score"])),
                ("Best", f'{s["best"][1]} · {pct(s["best"][0])}' if s["best"] else "–"),
                ("Models run", s["evaluated_by"]),
            ],
        })
        for i, m in enumerate(models):
            r = ms.get((m["id"], st["id"]))
            if r:
                set_edges.append({
                    "s": i, "t": j, "value": r["score"] / 100, "dashed": r["solved"] == 0,
                    "label": f'{r["score"]:.1f}\\%',
                    "info": [
                        ("Score", f'100·{r["c"]}/({r["n"]}·{r["N"]}) = {pct(r["score"])}'),
                        ("Solved", f'{r["solved"]} / {r["N"]}'),
                        ("Samples per problem", r["n"]),
                    ],
                    "title": f'{m["name"]} → {st["title"]}',
                })

    views = [{"key": "overview", "name": "Models → Problem sets",
              "sources": model_nodes, "targets": set_nodes, "edges": set_edges}]

    for st in sets:
        sp = [p for p in problems if p["set_id"] == st["id"]]
        if not sp:
            continue
        targets, edges = [], []
        for j, p in enumerate(sp):
            s = ps[p["id"]]
            label = f"P{j + 1}" + (f' · {p["title"]}' if p["title"] else "")
            targets.append({
                "id": p["id"], "label": label, "url": link("problem_page", problem_id=p["id"]),
                "sub": f'diff {num(s["difficulty"])} · solved by {s["solved_by"]}/{s["evaluated_by"]}',
                "value": s["difficulty"],
                "info": [
                    ("Difficulty", num(s["difficulty"]) + "  (1 − pass rate)"),
                    ("Pass rate", pct(None if s["pass_rate"] is None else 100 * s["pass_rate"])),
                    ("Solved by", f'{s["solved_by"]} / {s["evaluated_by"]} models'),
                ],
            })
            for i, m in enumerate(models):
                r = s["per_model"].get(m["id"])
                if r:
                    edges.append({
                        "s": i, "t": j, "value": r["c"] / r["k"], "dashed": r["c"] == 0,
                        "label": f'{r["c"]}/{r["k"]}',
                        "info": [("Correct", f'{r["c"]} / {r["k"]} samples'),
                                 ("Pass rate", pct(100 * r["c"] / r["k"]))],
                        "title": f'{m["name"]} → {label}',
                    })
        views.append({"key": f"set-{st['id']}", "name": f"Models → {st['title']}",
                      "sources": model_nodes, "targets": targets, "edges": edges})
    return views


# ================================================================ admin: auth

def admin_password():
    return os.environ.get("BOXED_ADMIN_PASSWORD", "")


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = request.form.get("csrf", "")
        if not token or not hmac.compare_digest(token, session.get("csrf", "")):
            abort(400, "Invalid CSRF token - reload the page and try again.")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    configured = bool(admin_password())
    if request.method == "POST" and configured:
        if hmac.compare_digest(request.form.get("password", "").encode(),
                               admin_password().encode()):
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
        flash("Wrong password.", "error")
    return render_template("admin/login.html", configured=configured)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


# ================================================================ admin: CRUD

def form_int(name, default=0):
    try:
        return int(request.form.get(name, default))
    except ValueError:
        return default


@app.route("/admin")
@admin_required
def admin():
    sets, problems, models, stats = load_all()
    return render_template("admin/dashboard.html", sets=sets, models=models, stats=stats)


@app.route("/admin/sets/new", methods=["GET", "POST"])
@app.route("/admin/sets/<int:set_id>", methods=["GET", "POST"])
@admin_required
def admin_set(set_id=None):
    d = db.get_db()
    st = db.get_set(d, set_id) if set_id else None
    if set_id and not st:
        abort(404)
    if request.method == "POST":
        if request.form.get("action") == "delete" and st:
            d.execute("DELETE FROM problem_sets WHERE id = ?", (set_id,))
            d.commit()
            flash(f'Deleted set "{st["title"]}".', "ok")
            return redirect(url_for("admin"))
        vals = (request.form.get("title", "").strip() or "Untitled set",
                request.form.get("subject", "math"),
                request.form.get("description", ""), form_int("position"))
        if st:
            d.execute("UPDATE problem_sets SET title=?, subject=?, description=?, position=? "
                      "WHERE id=?", (*vals, set_id))
        else:
            set_id = d.execute("INSERT INTO problem_sets (title, subject, description, position) "
                               "VALUES (?, ?, ?, ?)", vals).lastrowid
        d.commit()
        flash("Problem set saved.", "ok")
        return redirect(url_for("admin_set", set_id=set_id))
    problems = db.set_problems(d, set_id) if set_id else []
    return render_template("admin/set_form.html", st=st, problems=problems)


@app.route("/admin/problems/new", methods=["GET", "POST"])
@app.route("/admin/problems/<int:problem_id>", methods=["GET", "POST"])
@admin_required
def admin_problem(problem_id=None):
    d = db.get_db()
    p = db.get_problem(d, problem_id) if problem_id else None
    if problem_id and not p:
        abort(404)
    set_id = p["set_id"] if p else request.values.get("set_id", type=int)
    st = db.get_set(d, set_id) or abort(404)
    if request.method == "POST":
        if request.form.get("action") == "delete" and p:
            d.execute("DELETE FROM problems WHERE id = ?", (problem_id,))
            d.commit()
            flash("Problem deleted.", "ok")
            return redirect(url_for("admin_set", set_id=set_id))
        statement = request.form.get("statement", "").strip()
        answer = request.form.get("answer", "").strip()
        if not statement or not answer:
            flash("Statement and answer are both required.", "error")
            return render_template("admin/problem_form.html", p=request.form, st=st,
                                   problem_id=problem_id)
        position = form_int("position", -1)
        if position < 0:
            position = d.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM problems "
                                 "WHERE set_id = ?", (set_id,)).fetchone()[0]
        vals = (request.form.get("title", "").strip(), statement, answer,
                request.form.get("notes", ""), position)
        if p:
            d.execute("UPDATE problems SET title=?, statement=?, answer=?, notes=?, position=? "
                      "WHERE id=?", (*vals, problem_id))
        else:
            problem_id = d.execute("INSERT INTO problems (title, statement, answer, notes, "
                                   "position, set_id) VALUES (?, ?, ?, ?, ?, ?)",
                                   (*vals, set_id)).lastrowid
        d.commit()
        flash("Problem saved.", "ok")
        if request.form.get("action") == "save_new":
            return redirect(url_for("admin_problem", set_id=set_id))
        return redirect(url_for("admin_problem", problem_id=problem_id))
    return render_template("admin/problem_form.html", p=p, st=st, problem_id=problem_id)


@app.route("/admin/models/new", methods=["GET", "POST"])
@app.route("/admin/models/<int:model_id>", methods=["GET", "POST"])
@admin_required
def admin_model(model_id=None):
    d = db.get_db()
    m = db.get_model(d, model_id) if model_id else None
    if model_id and not m:
        abort(404)
    if request.method == "POST":
        if request.form.get("action") == "delete" and m:
            d.execute("DELETE FROM models WHERE id = ?", (model_id,))
            d.commit()
            flash(f'Deleted model "{m["name"]}" and its results.', "ok")
            return redirect(url_for("admin"))
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "error")
            return render_template("admin/model_form.html", m=request.form, model_id=model_id)
        vals = (name, request.form.get("params", "").strip(),
                request.form.get("family", "").strip(), request.form.get("notes", ""))
        try:
            if m:
                d.execute("UPDATE models SET name=?, params=?, family=?, notes=? WHERE id=?",
                          (*vals, model_id))
            else:
                model_id = d.execute("INSERT INTO models (name, params, family, notes) "
                                     "VALUES (?, ?, ?, ?)", vals).lastrowid
            d.commit()
        except db.sqlite3.IntegrityError:
            flash(f'A model named "{name}" already exists.', "error")
            return render_template("admin/model_form.html", m=request.form, model_id=model_id)
        flash("Model saved.", "ok")
        return redirect(url_for("admin"))
    return render_template("admin/model_form.html", m=m, model_id=model_id)


# ================================================================ admin: results

@app.route("/admin/results", methods=["GET", "POST"])
@admin_required
def admin_results():
    d = db.get_db()
    models, sets = db.all_models(d), db.all_sets(d)
    model_id = request.values.get("model_id", type=int)
    set_id = request.values.get("set_id", type=int)
    m = db.get_model(d, model_id) if model_id else None
    st = db.get_set(d, set_id) if set_id else None
    if not (m and st):
        return render_template("admin/results.html", models=models, sets=sets, m=m, st=st)

    problems = db.set_problems(d, set_id)
    existing = {}
    for p in problems:
        existing[p["id"]] = d.execute(
            "SELECT * FROM samples WHERE model_id=? AND problem_id=? ORDER BY sample_index",
            (model_id, p["id"])).fetchall()

    if request.method == "POST":
        n = max(1, min(64, form_int("n", 1)))
        action = request.form.get("action", "save")
        grid = {}
        for p in problems:
            grid[p["id"]] = []
            for i in range(n):
                ans = request.form.get(f"a-{p['id']}-{i}", "").strip()
                ok = request.form.get(f"c-{p['id']}-{i}") == "1"
                if action == "automark":
                    ok = scoring.same_answer(ans, p["answer"])
                old = existing[p["id"]]
                raw = old[i]["raw_output"] if i < len(old) else ""
                grid[p["id"]].append({"answer": ans, "correct": ok, "raw_output": raw})
        if action == "automark":
            flash("Marked answers that match the reference. Review, then save.", "ok")
            return render_template("admin/results.html", models=models, sets=sets, m=m, st=st,
                                   problems=problems, grid=grid, n=n)
        for pid, samples in grid.items():
            # rows left completely empty are not stored
            while samples and not samples[-1]["answer"] and not samples[-1]["correct"] \
                    and not samples[-1]["raw_output"]:
                samples.pop()
            db.replace_samples(d, model_id, pid, samples)
        d.commit()
        flash("Results saved.", "ok")
        return redirect(url_for("admin_results", model_id=model_id, set_id=set_id))

    n = request.args.get("n", type=int) or max(
        [len(v) for v in existing.values()] + [4])
    n = max(1, min(64, n))
    grid = {pid: [{"answer": s["answer"], "correct": bool(s["correct"]),
                   "raw_output": s["raw_output"]} for s in rows]
            for pid, rows in existing.items()}
    for rows in grid.values():
        rows.extend({"answer": "", "correct": False, "raw_output": ""}
                    for _ in range(n - len(rows)))
    return render_template("admin/results.html", models=models, sets=sets, m=m, st=st,
                           problems=problems, grid=grid, n=n)


IMPORT_EXAMPLE = """{
  "model": {"name": "Qwen2.5-Math-1.5B-Instruct", "params": "1.5B", "family": "Qwen"},
  "results": [
    {"problem_id": 1, "samples": [
      {"answer": "42", "correct": true},
      {"raw_output": "... so the answer is \\\\boxed{41}."}
    ]}
  ]
}"""


def import_results(d, payload):
    """Import one model's samples. A sample without "answer" gets it extracted
    from the last \\boxed{} of "raw_output"; one without "correct" is graded
    against the reference answer."""
    mdef = payload.get("model")
    if isinstance(mdef, str):
        mdef = {"name": mdef}
    if not isinstance(mdef, dict) or not mdef.get("name"):
        raise ValueError('"model" must be a name or an object with "name".')
    row = d.execute("SELECT id FROM models WHERE name = ?", (mdef["name"],)).fetchone()
    if row:
        model_id = row["id"]
    else:
        model_id = d.execute(
            "INSERT INTO models (name, params, family, notes) VALUES (?, ?, ?, ?)",
            (mdef["name"], mdef.get("params", ""), mdef.get("family", ""),
             mdef.get("notes", ""))).lastrowid
    count = 0
    for res in payload.get("results", []):
        p = db.get_problem(d, res.get("problem_id"))
        if not p:
            raise ValueError(f'Unknown problem_id {res.get("problem_id")!r}.')
        samples = []
        for s in res.get("samples", []):
            if isinstance(s, str):
                s = {"raw_output": s}
            raw = s.get("raw_output", "") or ""
            ans = s.get("answer")
            if ans is None:
                ans = scoring.extract_boxed(raw) or ""
            ok = s.get("correct")
            if ok is None:
                ok = scoring.same_answer(ans, p["answer"])
            samples.append({"answer": ans, "correct": bool(ok), "raw_output": raw})
        db.replace_samples(d, model_id, p["id"], samples)
        count += len(samples)
    return mdef["name"], count


@app.route("/admin/import", methods=["GET", "POST"])
@admin_required
def admin_import():
    text = ""
    if request.method == "POST":
        upload = request.files.get("file")
        text = upload.read().decode("utf-8") if upload and upload.filename else \
            request.form.get("json", "")
        d = db.get_db()
        try:
            payload = json.loads(text)
            batches = payload if isinstance(payload, list) else [payload]
            done = [import_results(d, b) for b in batches]
            d.commit()
            for name, count in done:
                flash(f"Imported {count} samples for {name}.", "ok")
            return redirect(url_for("admin"))
        except (ValueError, AttributeError, TypeError) as e:
            d.rollback()
            flash(f"Import failed: {e}", "error")
    return render_template("admin/import.html", text=text, example=IMPORT_EXAMPLE)


@app.route("/admin/export.json")
@admin_required
def admin_export():
    d = db.get_db()
    out = []
    for st in db.all_sets(d):
        out.append({
            "id": st["id"], "title": st["title"], "subject": st["subject"],
            "problems": [{"id": p["id"], "title": p["title"], "statement": p["statement"],
                          "answer": p["answer"]} for p in db.set_problems(d, st["id"])],
        })
    return Response(json.dumps({"sets": out}, ensure_ascii=False, indent=2),
                    mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=boxed-export.json"})


if __name__ == "__main__":
    port = int(os.environ.get("BOXED_PORT", 5000))
    if not admin_password():
        print(" * BOXED_ADMIN_PASSWORD is not set - the admin area is disabled.")
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("BOXED_DEBUG") == "1")
