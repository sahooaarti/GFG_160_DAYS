import os
import sys
from typing import Optional

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


def _prompt(prompt: str, default: Optional[str] = None) -> str:
    msg = f"{prompt}"
    if default is not None:
        msg += f" [{default}]"
    msg += ": "
    val = input(msg).strip()
    return val if val else (default or "")


def main() -> int:
    file_path = _prompt("Enter path to input content file")
    chapter = _prompt("Enter chapter title (blank to use file name)", "")
    num_questions_str = _prompt("Enter number of questions", "1")

    try:
        num_questions = int(num_questions_str)
    except Exception:
        num_questions = 1

    content = safe_read_file(file_path)
    derived_chapter = chapter or os.path.splitext(os.path.basename(file_path))[0]

    result = generate_questions_from_llm(
        content,
        derived_chapter,
        "google/gemini-2.5-flash",
        0.6,
        num_questions,
        "11",
        None,
    )

    print(__import__("json").dumps(result["questions"], ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

