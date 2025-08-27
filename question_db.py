import os
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2
    from psycopg2.extras import Json
    from psycopg2.pool import SimpleConnectionPool
except Exception as exc:  # pragma: no cover
    raise RuntimeError("psycopg2 is required for database operations") from exc


_POOL: SimpleConnectionPool = None  # type: ignore[assignment]


def _ensure_pool() -> None:
    global _POOL
    if _POOL is not None:
        return
    dbname = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    if not all([dbname, user, password, host, port]):
        raise EnvironmentError("Database environment variables are not fully set")
    _POOL = SimpleConnectionPool(1, 10, dbname=dbname, user=user, password=password, host=host, port=port)


@contextmanager
def get_conn():
    _ensure_pool()
    conn = _POOL.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _POOL.putconn(conn)


def init_db(schema_path: str) -> None:
    if not schema_path or not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with get_conn() as conn:
        with conn.cursor() as cur, open(schema_path, "r", encoding="utf-8") as f:
            cur.execute(f.read())


CATEGORY_MAP = {
    "mcq": 1,
    "multi": 2,
    "fill": 3,
    "match": 4,
    "subjective": 5,
    "integer": 6,
}


def _ensure_category(cur, qtype: str) -> int:
    category_id = CATEGORY_MAP.get(qtype)
    if not category_id:
        raise ValueError(f"Unknown question type: {qtype}")
    cur.execute(
        """
        INSERT INTO categories (category_id, question_type, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (category_id) DO NOTHING
        """,
        (category_id, qtype, f"{qtype} question"),
    )
    return category_id


def insert_question_batch(questions: List[Dict[str, Any]], common: Dict[str, Any]) -> List[int]:
    inserted_ids: List[int] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for q in questions:
                qtype = q.get("type")
                category_id = _ensure_category(cur, qtype)

                cur.execute(
                    """
                    INSERT INTO common_questions
                        (grade, subject_name, chapter, topic, category_id, question_type, difficulty, tokens_used, model, temperature)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        common.get("grade"),
                        common.get("subject_name"),
                        common.get("chapter"),
                        q.get("topic"),
                        category_id,
                        qtype,
                        q.get("difficulty"),
                        common.get("tokens_used", 0),
                        common.get("model"),
                        common.get("temperature"),
                    ),
                )
                question_id = cur.fetchone()[0]

                if qtype == "mcq":
                    cur.execute(
                        """
                        INSERT INTO mcq_questions (common_question_id, question, option_a, option_b, option_c, option_d, answer)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            question_id,
                            q.get("question"),
                            (q.get("options") or {}).get("A"),
                            (q.get("options") or {}).get("B"),
                            (q.get("options") or {}).get("C"),
                            (q.get("options") or {}).get("D"),
                            q.get("answer"),
                        ),
                    )
                elif qtype == "multi":
                    cur.execute(
                        """
                        INSERT INTO multi_questions (common_question_id, question, option_a, option_b, option_c, option_d, answers)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            question_id,
                            q.get("question"),
                            (q.get("options") or {}).get("A"),
                            (q.get("options") or {}).get("B"),
                            (q.get("options") or {}).get("C"),
                            (q.get("options") or {}).get("D"),
                            Json(q.get("answer")),
                        ),
                    )
                elif qtype == "fill":
                    cur.execute(
                        """
                        INSERT INTO fill_questions (common_question_id, question, answer)
                        VALUES (%s,%s,%s)
                        """,
                        (question_id, q.get("question"), q.get("answer")),
                    )
                elif qtype == "match":
                    pairs = q.get("pairs") or {"list_a": [], "list_b": []}
                    cur.execute(
                        """
                        INSERT INTO match_questions (
                            common_question_id, question, list_a, list_b,
                            option_a, option_b, option_c, option_d, answer
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            question_id,
                            q.get("question"),
                            Json(pairs.get("list_a", [])),
                            Json(pairs.get("list_b", [])),
                            Json((q.get("options") or {}).get("A", [])),
                            Json((q.get("options") or {}).get("B", [])),
                            Json((q.get("options") or {}).get("C", [])),
                            Json((q.get("options") or {}).get("D", [])),
                            q.get("answer"),
                        ),
                    )
                elif qtype == "subjective":
                    cur.execute(
                        """
                        INSERT INTO subjective_questions (common_question_id, question, answer)
                        VALUES (%s,%s,%s)
                        """,
                        (question_id, q.get("question"), q.get("answer", "")),
                    )
                elif qtype == "integer":
                    cur.execute(
                        """
                        INSERT INTO integer_questions (common_question_id, question, answer)
                        VALUES (%s,%s,%s)
                        """,
                        (question_id, q.get("question"), q.get("answer")),
                    )
                else:
                    raise ValueError(f"Unsupported question type: {qtype}")

                inserted_ids.append(question_id)

    return inserted_ids

