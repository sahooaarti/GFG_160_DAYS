import os
import sys
from typing import List, Optional

try:
    import chardet
except Exception:  # pragma: no cover
    chardet = None

from question_generator import generate_questions_from_llm


def safe_read_file(path: str) -> str:
    try:
        with open(path, "rb") as f:
            raw_data = f.read()
            encoding: Optional[str] = None
            if chardet is not None:
                try:
                    encoding = (chardet.detect(raw_data) or {}).get("encoding")
                except Exception:
                    encoding = None
            for enc in filter(None, [encoding, "utf-8", "latin-1"]):
                try:
                    return raw_data.decode(enc)
                except Exception:
                    continue
            return raw_data.decode("utf-8", errors="ignore")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}")


def _prompt(prompt: str, default: Optional[str] = None) -> str:
    msg = f"{prompt}"
    if default is not None:
        msg += f" [{default}]"
    msg += ": "
    val = input(msg).strip()
    return val if val else (default or "")


def _parse_types(types_csv: str) -> Optional[List[str]]:
    types_csv = (types_csv or "").strip()
    if not types_csv:
        return None
    return [t.strip() for t in types_csv.split(",") if t.strip()]


def _parse_timeout(timeout_csv: str):
    parts = [p.strip() for p in (timeout_csv or "").split(",") if p.strip()]
    if len(parts) == 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except Exception:
            pass
    try:
        return int(parts[0])
    except Exception:
        return (10, 60)


def main() -> int:
    file_path = _prompt("Enter path to input content file")
    chapter = _prompt("Enter chapter title (blank to use file name)", "")
    grade = _prompt("Enter grade", "11")
    model = _prompt("Enter model id", "google/gemini-2.5-flash")
    temperature_str = _prompt("Enter temperature (float)", "0.6")
    num_questions_str = _prompt("Enter number of questions (int)", "1")
    types_csv = _prompt("Allowed types CSV (mcq,multi,fill,match,subjective) or blank for mix", "")
    max_input_tokens_str = _prompt("Max input tokens", "6000")
    max_output_tokens_str = _prompt("Max output tokens", "1000")
    timeout_csv = _prompt("Timeout seconds as connect,read", "10,60")

    try:
        temperature = float(temperature_str)
    except Exception:
        temperature = 0.6
    try:
        num_questions = int(num_questions_str)
    except Exception:
        num_questions = 1
    try:
        max_input_tokens = int(max_input_tokens_str)
    except Exception:
        max_input_tokens = 6000
    try:
        max_output_tokens = int(max_output_tokens_str)
    except Exception:
        max_output_tokens = 1000

    content = safe_read_file(file_path)
    allowed_types = _parse_types(types_csv)
    timeout = _parse_timeout(timeout_csv)

    derived_chapter = chapter or os.path.splitext(os.path.basename(file_path))[0]

    result = generate_questions_from_llm(
        content,
        derived_chapter,
        model,
        temperature,
        num_questions,
        grade,
        allowed_types,
        max_output_tokens=max_output_tokens,
        max_input_tokens=max_input_tokens,
        timeout=timeout,
    )

    print(__import__("json").dumps(result["questions"], ensure_ascii=False, indent=2))

    insert_db_answer = _prompt("Insert generated questions into DB? (y/N)", "N").lower()
    if insert_db_answer == "y":
        try:
            from question_db import init_db, insert_question_batch
        except Exception as exc:  # pragma: no cover
            print(f"DB import failed: {exc}", file=sys.stderr)
            return 0

        schema_path = _prompt("Path to schema.sql (blank to skip init)", "")
        if schema_path:
            try:
                init_db(schema_path)
            except Exception as exc:
                print(f"DB init failed (continuing): {exc}", file=sys.stderr)

        common_base = {
            "grade": grade,
            "chapter": derived_chapter,
            "subject_name": os.getenv("SUBJECT_NAME", ""),
            "model": result["model"],
            "temperature": result["temperature"],
            "tokens_used": result.get("input_tokens_estimate", 0),
        }

        insert_question_batch(result["questions"], common_base)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

