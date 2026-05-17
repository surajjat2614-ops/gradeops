<<<<<<< HEAD
import os
import json
import sqlite3
from contextlib import contextmanager

# Fetch from environment, default to a standard local postgres URL for development
DATABASE_URL = os.getenv("DATABASE_URL", "gradeops.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = dict_factory
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    username VARCHAR(255) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL
        );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    exam_name VARCHAR(255) NOT NULL,
                    owner VARCHAR(255) NOT NULL,
                    question_paper_path TEXT DEFAULT '',
                    marking_scheme_path TEXT,
                    answer_sheet_paths TEXT DEFAULT '[]',
                    extracted_questions TEXT DEFAULT '[]',
                    coordinates TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
                CREATE TABLE IF NOT EXISTS grading_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    student_id VARCHAR(255) DEFAULT '',
                    question_id VARCHAR(255) DEFAULT '',
                    proposed_score REAL DEFAULT 0,
                    justification TEXT DEFAULT '',
                    needs_review BOOLEAN DEFAULT FALSE,
                    error_axes TEXT DEFAULT '[]',
                    transcription TEXT DEFAULT '',
                    snippet_path TEXT DEFAULT '',
                    accuracy REAL DEFAULT 0,
                    rubric TEXT DEFAULT '{}',
                    verification_passed BOOLEAN,
                    verification_feedback TEXT,
                    review_status VARCHAR(50) DEFAULT 'pending'
        );
                CREATE TABLE IF NOT EXISTS plagiarism_flags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    student_a VARCHAR(255) DEFAULT '',
                    student_b VARCHAR(255) DEFAULT '',
                    confidence REAL DEFAULT 0,
                    shared_error_axes TEXT DEFAULT '[]',
                    reason TEXT DEFAULT ''
        );
                CREATE TABLE IF NOT EXISTS rubric_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    question_id VARCHAR(255) NOT NULL,
                    rubric_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, question_id)
        );
            """)


# ── Users ──

def get_user(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                "SELECT username, password_hash, role FROM users WHERE username=?",
                (username,),
        )
        return cur.fetchone()


def user_exists(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
        return cur.fetchone() is not None


def create_user(username, password_hash, role):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
        )


def migrate_users_from_json(json_path):
    import pathlib
    path = pathlib.Path(json_path)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for username, info in data.items():
        if not user_exists(username):
            create_user(username, info["password_hash"], info["role"])


# ── Sessions ──

def create_session(session_id, exam_name, owner, question_paper_path, answer_sheet_paths, marking_scheme_path=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                """INSERT INTO sessions
                   (session_id, exam_name, owner, question_paper_path, marking_scheme_path, answer_sheet_paths)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, exam_name, owner, question_paper_path, marking_scheme_path, json.dumps(answer_sheet_paths)),
        )


def get_session(session_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        row["answer_sheet_paths"] = json.loads(row["answer_sheet_paths"])
        row["extracted_questions"] = json.loads(row["extracted_questions"])
        row["coordinates"] = json.loads(row["coordinates"])

        cur.execute(
                "SELECT * FROM grading_results WHERE session_id=? ORDER BY id", (session_id,)
        )
        results = cur.fetchall()
        for r in results:
            r["error_axes"] = json.loads(r["error_axes"]) if r["error_axes"] else []
            r["rubric"] = json.loads(r["rubric"]) if r["rubric"] else None
            r["needs_review"] = bool(r["needs_review"])
            if r["verification_passed"] is not None:
                r["verification_passed"] = bool(r["verification_passed"])
        row["results"] = results
        row["review_queue"] = [r for r in results if r.get("accuracy", 1) < 0.7 or r.get("needs_review")]

        cur.execute(
                "SELECT * FROM plagiarism_flags WHERE session_id=? ORDER BY id", (session_id,)
        )
        flags = cur.fetchall()
        for f in flags:
            f["shared_error_axes"] = json.loads(f["shared_error_axes"]) if f["shared_error_axes"] else []
            f["pair"] = (f["student_a"], f["student_b"])
        row["plagiarism_flags"] = flags
        return row


def update_session_questions(session_id, extracted_questions):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET extracted_questions=? WHERE session_id=?",
                (json.dumps(extracted_questions), session_id),
        )


def update_session_coordinates(session_id, coordinates):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET coordinates=? WHERE session_id=?",
                (json.dumps(coordinates), session_id),
        )


# ── Results ──

def save_results(session_id, results):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM grading_results WHERE session_id=?", (session_id,))
        for r in results:
            vp = r.get("verification_passed")
            cur.execute(
                """INSERT INTO grading_results
                       (session_id, student_id, question_id, proposed_score, justification,
                        needs_review, error_axes, transcription, snippet_path, accuracy,
                        rubric, verification_passed, verification_feedback)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        r.get("student_id", ""),
                        r.get("question_id", ""),
                        r.get("proposed_score", 0),
                        r.get("justification", ""),
                        bool(r.get("needs_review")),
                        json.dumps(r.get("error_axes", [])),
                        r.get("transcription", ""),
                        r.get("snippet_path", ""),
                        r.get("accuracy", 0),
                        json.dumps(r.get("rubric")) if r.get("rubric") else "{}",
                        vp if vp is not None else None,
                        r.get("verification_feedback"),
                    ),
        )


def save_plagiarism_flags(session_id, flags):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM plagiarism_flags WHERE session_id=?", (session_id,))
        for f in flags:
            pair = f.get("pair", ("", ""))
            cur.execute(
                """INSERT INTO plagiarism_flags
                       (session_id, student_a, student_b, confidence, shared_error_axes, reason)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (session_id, pair[0], pair[1], f.get("confidence", 0),
                     json.dumps(f.get("shared_error_axes", [])), f.get("reason", "")),
        )


def update_result_review(result_id, review_status, new_score=None):
    with get_db() as conn:
        cur = conn.cursor()
        if new_score is not None:
            cur.execute(
                    "UPDATE grading_results SET review_status=?, proposed_score=? WHERE id=?",
                    (review_status, new_score, result_id),
        )
        else:
            cur.execute(
                    "UPDATE grading_results SET review_status=? WHERE id=?",
                    (review_status, result_id),
        )
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        return cur.fetchone()


# ── Rubric Templates ──

def save_rubric_template(session_id, question_id, rubric_dict):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO rubric_templates (session_id, question_id, rubric_json)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, question_id) DO UPDATE SET rubric_json=excluded.rubric_json""",
            (session_id, question_id, json.dumps(rubric_dict)),
        )


def get_rubric_templates(session_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM rubric_templates WHERE session_id=?", (session_id,))
        rows = cur.fetchall()
        for r in rows:
            r["rubric_json"] = json.loads(r["rubric_json"]) if r["rubric_json"] else {}
        return rows


def get_rubric_template(session_id, question_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rubric_templates WHERE session_id=? AND question_id=?",
            (session_id, question_id),
        )
        row = cur.fetchone()
        if row:
            row["rubric_json"] = json.loads(row["rubric_json"]) if row["rubric_json"] else {}
        return row


def delete_rubric_template(session_id, question_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM rubric_templates WHERE session_id=? AND question_id=?",
            (session_id, question_id),
        )


# ── Single Result Operations ──

def get_result_by_id(result_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        row = cur.fetchone()
        if row:
            row["error_axes"] = json.loads(row["error_axes"]) if row["error_axes"] else []
            row["rubric"] = json.loads(row["rubric"]) if row["rubric"] else None
            row["needs_review"] = bool(row["needs_review"])
            if row["verification_passed"] is not None:
                row["verification_passed"] = bool(row["verification_passed"])
        return row


def update_single_result(result_id, updates):
    with get_db() as conn:
        cur = conn.cursor()
        vp = updates.get("verification_passed")
        cur.execute(
            """UPDATE grading_results
               SET proposed_score=?, justification=?, needs_review=?, error_axes=?,
                   transcription=?, accuracy=?, rubric=?,
                   verification_passed=?, verification_feedback=?, review_status='pending'
               WHERE id=?""",
            (
                updates.get("proposed_score", 0),
                updates.get("justification", ""),
                bool(updates.get("needs_review")),
                json.dumps(updates.get("error_axes", [])),
                updates.get("transcription", ""),
                updates.get("accuracy", 0),
                json.dumps(updates.get("rubric")) if updates.get("rubric") else "{}",
                vp if vp is not None else None,
                updates.get("verification_feedback"),
                result_id,
            ),
        )
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        row = cur.fetchone()
        if row:
            row["error_axes"] = json.loads(row["error_axes"]) if row["error_axes"] else []
            row["rubric"] = json.loads(row["rubric"]) if row["rubric"] else None
            row["needs_review"] = bool(row["needs_review"])
        return row
=======
import os
import json
import sqlite3
from contextlib import contextmanager

# Fetch from environment, default to a standard local postgres URL for development
DATABASE_URL = os.getenv("DATABASE_URL", "gradeops.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = dict_factory
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    username VARCHAR(255) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL
        );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    exam_name VARCHAR(255) NOT NULL,
                    owner VARCHAR(255) NOT NULL,
                    question_paper_path TEXT DEFAULT '',
                    marking_scheme_path TEXT,
                    answer_sheet_paths TEXT DEFAULT '[]',
                    extracted_questions TEXT DEFAULT '[]',
                    coordinates TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
                CREATE TABLE IF NOT EXISTS grading_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    student_id VARCHAR(255) DEFAULT '',
                    question_id VARCHAR(255) DEFAULT '',
                    proposed_score REAL DEFAULT 0,
                    justification TEXT DEFAULT '',
                    needs_review BOOLEAN DEFAULT FALSE,
                    error_axes TEXT DEFAULT '[]',
                    transcription TEXT DEFAULT '',
                    snippet_path TEXT DEFAULT '',
                    accuracy REAL DEFAULT 0,
                    rubric TEXT DEFAULT '{}',
                    verification_passed BOOLEAN,
                    verification_feedback TEXT,
                    review_status VARCHAR(50) DEFAULT 'pending'
        );
                CREATE TABLE IF NOT EXISTS plagiarism_flags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    student_a VARCHAR(255) DEFAULT '',
                    student_b VARCHAR(255) DEFAULT '',
                    confidence REAL DEFAULT 0,
                    shared_error_axes TEXT DEFAULT '[]',
                    reason TEXT DEFAULT ''
        );
                CREATE TABLE IF NOT EXISTS rubric_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    question_id VARCHAR(255) NOT NULL,
                    rubric_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, question_id)
        );
            """)


# ── Users ──

def get_user(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                "SELECT username, password_hash, role FROM users WHERE username=?",
                (username,),
        )
        return cur.fetchone()


def user_exists(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
        return cur.fetchone() is not None


def create_user(username, password_hash, role):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
        )


def migrate_users_from_json(json_path):
    import pathlib
    path = pathlib.Path(json_path)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for username, info in data.items():
        if not user_exists(username):
            create_user(username, info["password_hash"], info["role"])


# ── Sessions ──

def create_session(session_id, exam_name, owner, question_paper_path, answer_sheet_paths, marking_scheme_path=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
                """INSERT INTO sessions
                   (session_id, exam_name, owner, question_paper_path, marking_scheme_path, answer_sheet_paths)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, exam_name, owner, question_paper_path, marking_scheme_path, json.dumps(answer_sheet_paths)),
        )


def get_session(session_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        row["answer_sheet_paths"] = json.loads(row["answer_sheet_paths"])
        row["extracted_questions"] = json.loads(row["extracted_questions"])
        row["coordinates"] = json.loads(row["coordinates"])

        cur.execute(
                "SELECT * FROM grading_results WHERE session_id=? ORDER BY id", (session_id,)
        )
        results = cur.fetchall()
        for r in results:
            r["error_axes"] = json.loads(r["error_axes"]) if r["error_axes"] else []
            r["rubric"] = json.loads(r["rubric"]) if r["rubric"] else None
            r["needs_review"] = bool(r["needs_review"])
            if r["verification_passed"] is not None:
                r["verification_passed"] = bool(r["verification_passed"])
        row["results"] = results
        row["review_queue"] = [r for r in results if r.get("accuracy", 1) < 0.7 or r.get("needs_review")]

        cur.execute(
                "SELECT * FROM plagiarism_flags WHERE session_id=? ORDER BY id", (session_id,)
        )
        flags = cur.fetchall()
        for f in flags:
            f["shared_error_axes"] = json.loads(f["shared_error_axes"]) if f["shared_error_axes"] else []
            f["pair"] = (f["student_a"], f["student_b"])
        row["plagiarism_flags"] = flags
        return row


def update_session_questions(session_id, extracted_questions):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET extracted_questions=? WHERE session_id=?",
                (json.dumps(extracted_questions), session_id),
        )


def update_session_coordinates(session_id, coordinates):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sessions SET coordinates=? WHERE session_id=?",
                (json.dumps(coordinates), session_id),
        )


# ── Results ──

def save_results(session_id, results):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM grading_results WHERE session_id=?", (session_id,))
        for r in results:
            vp = r.get("verification_passed")
            cur.execute(
                """INSERT INTO grading_results
                       (session_id, student_id, question_id, proposed_score, justification,
                        needs_review, error_axes, transcription, snippet_path, accuracy,
                        rubric, verification_passed, verification_feedback)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        r.get("student_id", ""),
                        r.get("question_id", ""),
                        r.get("proposed_score", 0),
                        r.get("justification", ""),
                        bool(r.get("needs_review")),
                        json.dumps(r.get("error_axes", [])),
                        r.get("transcription", ""),
                        r.get("snippet_path", ""),
                        r.get("accuracy", 0),
                        json.dumps(r.get("rubric")) if r.get("rubric") else "{}",
                        vp if vp is not None else None,
                        r.get("verification_feedback"),
                    ),
        )


def save_plagiarism_flags(session_id, flags):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM plagiarism_flags WHERE session_id=?", (session_id,))
        for f in flags:
            pair = f.get("pair", ("", ""))
            cur.execute(
                """INSERT INTO plagiarism_flags
                       (session_id, student_a, student_b, confidence, shared_error_axes, reason)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (session_id, pair[0], pair[1], f.get("confidence", 0),
                     json.dumps(f.get("shared_error_axes", [])), f.get("reason", "")),
        )


def update_result_review(result_id, review_status, new_score=None):
    with get_db() as conn:
        cur = conn.cursor()
        if new_score is not None:
            cur.execute(
                    "UPDATE grading_results SET review_status=?, proposed_score=? WHERE id=?",
                    (review_status, new_score, result_id),
        )
        else:
            cur.execute(
                    "UPDATE grading_results SET review_status=? WHERE id=?",
                    (review_status, result_id),
        )
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        return cur.fetchone()


# ── Rubric Templates ──

def save_rubric_template(session_id, question_id, rubric_dict):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO rubric_templates (session_id, question_id, rubric_json)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, question_id) DO UPDATE SET rubric_json=excluded.rubric_json""",
            (session_id, question_id, json.dumps(rubric_dict)),
        )


def get_rubric_templates(session_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM rubric_templates WHERE session_id=?", (session_id,))
        rows = cur.fetchall()
        for r in rows:
            r["rubric_json"] = json.loads(r["rubric_json"]) if r["rubric_json"] else {}
        return rows


def get_rubric_template(session_id, question_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rubric_templates WHERE session_id=? AND question_id=?",
            (session_id, question_id),
        )
        row = cur.fetchone()
        if row:
            row["rubric_json"] = json.loads(row["rubric_json"]) if row["rubric_json"] else {}
        return row


def delete_rubric_template(session_id, question_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM rubric_templates WHERE session_id=? AND question_id=?",
            (session_id, question_id),
        )


# ── Single Result Operations ──

def get_result_by_id(result_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        row = cur.fetchone()
        if row:
            row["error_axes"] = json.loads(row["error_axes"]) if row["error_axes"] else []
            row["rubric"] = json.loads(row["rubric"]) if row["rubric"] else None
            row["needs_review"] = bool(row["needs_review"])
            if row["verification_passed"] is not None:
                row["verification_passed"] = bool(row["verification_passed"])
        return row


def update_single_result(result_id, updates):
    with get_db() as conn:
        cur = conn.cursor()
        vp = updates.get("verification_passed")
        cur.execute(
            """UPDATE grading_results
               SET proposed_score=?, justification=?, needs_review=?, error_axes=?,
                   transcription=?, accuracy=?, rubric=?,
                   verification_passed=?, verification_feedback=?, review_status='pending'
               WHERE id=?""",
            (
                updates.get("proposed_score", 0),
                updates.get("justification", ""),
                bool(updates.get("needs_review")),
                json.dumps(updates.get("error_axes", [])),
                updates.get("transcription", ""),
                updates.get("accuracy", 0),
                json.dumps(updates.get("rubric")) if updates.get("rubric") else "{}",
                vp if vp is not None else None,
                updates.get("verification_feedback"),
                result_id,
            ),
        )
        cur.execute("SELECT * FROM grading_results WHERE id=?", (result_id,))
        row = cur.fetchone()
        if row:
            row["error_axes"] = json.loads(row["error_axes"]) if row["error_axes"] else []
            row["rubric"] = json.loads(row["rubric"]) if row["rubric"] else None
            row["needs_review"] = bool(row["needs_review"])
        return row
>>>>>>> 15b1898f1ea7244db1b396e1e9d47837e0f8d22b
