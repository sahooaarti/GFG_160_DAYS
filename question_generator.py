import json
import math
import os
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv


load_dotenv()


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_OUTPUT_TOKENS = 1000
DEFAULT_TIMEOUT_SECONDS = (10, 60)


question_schema: Dict[str, Any] = {
    "name": "questions",
    "strict": True,
    "schema": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "pairs": {
                    "type": "object",
                    "description": "For match questions, provide labeled pairs for matching.",
                    "properties": {
                        "list_a": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Left-hand items, labeled A), B), C)..."
                        },
                        "list_b": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Right-hand items, labeled 1), 2), 3)..."
                        }
                    },
                    "required": ["list_a", "list_b"],
                    "additionalProperties": False
                },
                "options": {
                    "description": "Options differ by question type (mcq/multi vs match).",
                    "type": "object"
                },
                "answer": {
                    "description": "Correct answer(s) depending on question type."
                },
                "topic": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["mcq", "multi", "integer", "fill", "match", "subjective"]
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["easy", "medium", "hard"]
                },
                "grade": {"type": ["string", "integer"]}
            },
            "required": ["grade", "question", "answer", "topic", "type", "difficulty"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"type": {"const": "mcq"}}},
                    "then": {
                        "properties": {
                            "options": {
                                "type": "object",
                                "additionalProperties": {"type": "string"}
                            },
                            "answer": {"type": "string"}
                        }
                    }
                },
                {
                    "if": {"properties": {"type": {"const": "multi"}}},
                    "then": {
                        "properties": {
                            "options": {
                                "type": "object",
                                "additionalProperties": {"type": "string"}
                            },
                            "answer": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 2
                            }
                        }
                    }
                },
                {
                    "if": {"properties": {"type": {"const": "match"}}},
                    "then": {
                        "properties": {
                            "options": {
                                "type": "object",
                                "properties": {
                                    "A": {"type": "array", "items": {"type": "string"}},
                                    "B": {"type": "array", "items": {"type": "string"}},
                                    "C": {"type": "array", "items": {"type": "string"}},
                                    "D": {"type": "array", "items": {"type": "string"}}
                                },
                                "required": ["A", "B", "C", "D"],
                                "additionalProperties": False
                            },
                            "answer": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1
                            }
                        }
                    }
                },
                {
                    "if": {"properties": {"type": {"enum": ["fill", "subjective"]}}},
                    "then": {
                        "properties": {
                            "options": {"type": "null"},
                            "answer": {"type": ["string", "number"]}
                        }
                    }
                }
            ]
        }
    }
}


def _estimate_tokens_from_text_length(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _truncate_text_by_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    approx_max_chars = max_tokens * 4
    if len(text) <= approx_max_chars:
        return text
    return text[:approx_max_chars]


def _create_session(total_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    status_forcelist = (408, 409, 429, 500, 502, 503, 504)
    retry = Retry(
        total=total_retries,
        read=total_retries,
        connect=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def build_dynamic_prompt(
    chapter_title: str,
    context: str,
    num_of_questions: int,
    grade: str,
    question_types: Optional[List[str]] = None,
) -> str:
    types_text = (
        f"Only generate these types: {', '.join(question_types)}."
        if question_types
        else "Use a balanced mix of mcq, multi, integer, fill, match, and subjective."
    )

    return f"""
You are a question generator.

Input:
- Chapter: "{chapter_title}"
- Content: "{context}"

Task:
- Generate {num_of_questions} questions for Grade: {grade} students.
- {types_text}
- Each question must include: question, options (if required), answer, topic(keywords inside the content provided), type, difficulty, grade.
- Difficulty must be one of: easy, medium, hard.


Formatting Rules:
• MCQ → "answer" must be exactly one option key (e.g., "A").
• Multi → "answer" must be an array with TWO OR MORE correct option keys (e.g., ["A","C"]).
• Match:
  - 'pairs' strictly:
    • 'list_a' labeled as A), B), C), D)...
    • 'list_b' labeled as 1), 2), 3)...
  - 'options':
    • Must contain exactly four keys: A, B, C, D.
    • Each key maps to a list of 4 strings, each string a mapping like "A-4", "B-1", "C-2", "D-3".
  - 'answer': a single string — the correct option key (e.g., "A").
• Fill → answer is a string or numeric value, no options.
• Subjective → answer is a short string.

Return ONLY a **pure JSON array** following the schema provided. No explanations, no extra text.
"""


def generate_questions_from_llm(
    context: str,
    chapter_title: str,
    model: str,
    temperature: float,
    num_of_questions: int,
    grade: str,
    allowed_types: Optional[List[str]] = None,
    *,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_input_tokens: Optional[int] = None,
    timeout: Any = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise EnvironmentError("Missing OPENROUTER_API_KEY in environment")

    allowed = {"mcq", "multi", "integer", "fill", "match", "subjective"}
    if allowed_types:
        invalid = [t for t in allowed_types if t not in allowed]
        if invalid:
            raise ValueError(f"Invalid question types: {invalid}")

    if max_input_tokens is None:
        max_input_tokens = 6000

    truncated_context = _truncate_text_by_tokens(context, max_input_tokens)
    prompt = build_dynamic_prompt(chapter_title, truncated_context, num_of_questions, grade, allowed_types)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max(1, min(int(max_output_tokens), 2000)),
        "temperature": float(temperature),
        "response_format": {
            "type": "json_schema",
            "json_schema": question_schema,
        },
    }

    session = _create_session()
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    response = session.post(OPENROUTER_URL, headers=headers, data=json.dumps(payload), timeout=timeout)

    if not response.ok:
        try:
            error_data = response.json()
            message = error_data.get("error", {}).get("message") or error_data
        except Exception:
            message = response.text
        raise RuntimeError(f"OpenRouter API Error {response.status_code}: {message}")

    response_json = response.json()

    raw_content = None
    try:
        raw_content = response_json["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected API response format: missing content. Error: {exc}")

    questions: List[Dict[str, Any]]
    try:
        questions = json.loads(raw_content)
    except Exception:
        start = raw_content.find("[")
        end = raw_content.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Model did not return a valid JSON array")
        questions = json.loads(raw_content[start : end + 1])

    if not isinstance(questions, list):
        raise ValueError("Parsed content is not a JSON array of questions")

    return {
        "questions": questions,
        "chapter": chapter_title,
        "model": model,
        "temperature": temperature,
        "grade": grade,
        "raw_output": response_json,
        "input_tokens_estimate": _estimate_tokens_from_text_length(truncated_context),
        "output_tokens_limit": payload["max_tokens"],
    }

