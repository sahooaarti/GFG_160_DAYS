import argparse
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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate questions from content using an LLM")
    parser.add_argument("file", help="Path to input content file")
    parser.add_argument("--chapter", default="", help="Chapter title")
    parser.add_argument("--grade", default="11", help="Grade or level")
    parser.add_argument("--model", default="google/gemini-2.5-flash", help="OpenRouter model id")
    parser.add_argument("--temperature", type=float, default=0.6, help="Sampling temperature")
    parser.add_argument("--num-questions", type=int, default=1, help="Number of questions to generate")
    parser.add_argument("--types", default="", help="Comma-separated allowed types (mcq,multi,fill,match,subjective)")
    parser.add_argument("--max-input-tokens", type=int, default=6000, help="Max input tokens used from content")
    parser.add_argument("--max-output-tokens", type=int, default=1000, help="Max output tokens from model")
    parser.add_argument("--timeout", default="10,60", help="Timeout seconds as connect,read (e.g., 10,60)")
    parser.add_argument("--insert-db", action="store_true", help="Insert generated questions into the database")
    parser.add_argument("--schema", default="", help="Optional path to schema.sql to init DB once")
    return parser.parse_args(argv)


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


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    content = safe_read_file(args.file)

    allowed_types = _parse_types(args.types)
    timeout = _parse_timeout(args.timeout)

    result = generate_questions_from_llm(
        content,
        args.chapter or os.path.splitext(os.path.basename(args.file))[0],
        args.model,
        args.temperature,
        args.num_questions,
        args.grade,
        allowed_types,
        max_output_tokens=args.max_output_tokens,
        max_input_tokens=args.max_input_tokens,
        timeout=timeout,
    )

    print(json_dump := __import__("json").dumps(result["questions"], ensure_ascii=False, indent=2))

    if args.insert_db:
        try:
            from question_db import init_db, insert_question_batch
        except Exception as exc:  # pragma: no cover
            print(f"DB import failed: {exc}", file=sys.stderr)
            return 0

        if args.schema:
            try:
                init_db(args.schema)
            except Exception as exc:
                print(f"DB init failed (continuing): {exc}", file=sys.stderr)

        common_base = {
            "grade": args.grade,
            "chapter": args.chapter or os.path.splitext(os.path.basename(args.file))[0],
            "subject_name": os.getenv("SUBJECT_NAME", ""),
            "model": result["model"],
            "temperature": result["temperature"],
            "tokens_used": result.get("input_tokens_estimate", 0),
        }

        insert_question_batch(result["questions"], common_base)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

