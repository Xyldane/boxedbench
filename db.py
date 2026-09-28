"""SQLite storage for \\boxed{}.

Tables
------
problem_sets  a group of similar problems; scores are computed per set
problems      one question with a reference answer (LaTeX)
models        an LLM being benchmarked
samples       one sampled answer of a model to a problem (correct / wrong)
"""
import os
import sqlite3

from flask import g

DB_PATH = os.environ.get(
    "BOXED_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "boxed.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS problem_sets (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT 'math',
    description TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS problems (
    id        INTEGER PRIMARY KEY,
    set_id    INTEGER NOT NULL REFERENCES problem_sets(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL DEFAULT 0,
    title     TEXT NOT NULL DEFAULT '',
    statement TEXT NOT NULL,
    answer    TEXT NOT NULL,
    notes     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS models (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    params TEXT NOT NULL DEFAULT '',
    family TEXT NOT NULL DEFAULT '',
    notes  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS samples (
    id           INTEGER PRIMARY KEY,
    model_id     INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    problem_id   INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    sample_index INTEGER NOT NULL,
    answer       TEXT NOT NULL DEFAULT '',
    correct      INTEGER NOT NULL DEFAULT 0,
    raw_output   TEXT NOT NULL DEFAULT '',
    UNIQUE (model_id, problem_id, sample_index)
);

CREATE INDEX IF NOT EXISTS idx_problems_set ON problems(set_id, position);
CREATE INDEX IF NOT EXISTS idx_samples_problem ON samples(problem_id);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path=None):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- queries

def all_sets(db):
    return db.execute(
        """SELECT s.*, (SELECT COUNT(*) FROM problems p WHERE p.set_id = s.id) AS n_problems
           FROM problem_sets s ORDER BY s.position, s.id"""
    ).fetchall()


def get_set(db, set_id):
    return db.execute("SELECT * FROM problem_sets WHERE id = ?", (set_id,)).fetchone()


def set_problems(db, set_id):
    return db.execute(
        "SELECT * FROM problems WHERE set_id = ? ORDER BY position, id", (set_id,)
    ).fetchall()


def all_problems(db):
    return db.execute("SELECT * FROM problems ORDER BY set_id, position, id").fetchall()


def get_problem(db, problem_id):
    return db.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()


def all_models(db):
    return db.execute("SELECT * FROM models ORDER BY name COLLATE NOCASE").fetchall()


def get_model(db, model_id):
    return db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()


def all_samples(db):
    return db.execute(
        "SELECT * FROM samples ORDER BY model_id, problem_id, sample_index"
    ).fetchall()


def problem_samples(db, problem_id):
    return db.execute(
        "SELECT * FROM samples WHERE problem_id = ? ORDER BY model_id, sample_index",
        (problem_id,),
    ).fetchall()


def replace_samples(db, model_id, problem_id, samples):
    """Replace every sample of (model, problem) with `samples`
    (a list of dicts with answer / correct / raw_output)."""
    db.execute(
        "DELETE FROM samples WHERE model_id = ? AND problem_id = ?", (model_id, problem_id)
    )
    db.executemany(
        """INSERT INTO samples (model_id, problem_id, sample_index, answer, correct, raw_output)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (model_id, problem_id, i, s.get("answer", ""), 1 if s.get("correct") else 0,
             s.get("raw_output", ""))
            for i, s in enumerate(samples)
        ],
    )
