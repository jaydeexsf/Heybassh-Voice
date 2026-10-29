"""British English curriculum, student progress, and webhook payloads.

Mirrors the n8n workflow in Heybassh_British_English_Teacher_corrected.json:
ElevenLabs (or the local Pipecat bot) loads the current lesson, then posts
scores so the student can advance when they pass with 70 or more.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRICULUM_TOTAL_LESSONS = 22
PASS_SCORE = 70
DEFAULT_STUDENT_ID = "john"

CURRICULUM: list[dict[str, Any]] = [
    {
        "lesson": 1,
        "title": "Initial English Assessment",
        "module": "Assessment",
        "objective": "Assess the student's speaking, grammar, vocabulary, pronunciation, listening and confidence.",
        "topics": ["Speaking", "Grammar", "Vocabulary", "Pronunciation", "Listening", "Confidence"],
    },
    {
        "lesson": 2,
        "title": "Sentence Structure",
        "module": "Grammar Foundations",
        "objective": "Teach the student how to construct clear and grammatically correct English sentences.",
        "topics": ["Subject", "Verb", "Object", "Word order", "Sentence formation"],
    },
    {
        "lesson": 3,
        "title": "Present Simple",
        "module": "Core Tenses",
        "objective": "Teach when and how to use the present simple.",
        "topics": [
            "Positive sentences",
            "Negative sentences",
            "Questions",
            "Third-person singular",
            "Daily routines",
        ],
    },
    {
        "lesson": 4,
        "title": "Present Continuous",
        "module": "Core Tenses",
        "objective": "Teach how to describe actions happening now and temporary situations.",
        "topics": [
            "am/is/are",
            "Verb-ing",
            "Questions",
            "Negative sentences",
            "Present simple vs present continuous",
        ],
    },
    {
        "lesson": 5,
        "title": "Past Simple",
        "module": "Core Tenses",
        "objective": "Teach how to talk about completed actions in the past.",
        "topics": [
            "Regular verbs",
            "Irregular verbs",
            "Questions",
            "Negative sentences",
            "Past time expressions",
        ],
    },
    {
        "lesson": 6,
        "title": "Future Forms",
        "module": "Core Tenses",
        "objective": "Teach different ways of talking about future events and plans.",
        "topics": ["Will", "Going to", "Future plans", "Predictions"],
    },
    {
        "lesson": 7,
        "title": "Articles",
        "module": "Grammar Accuracy",
        "objective": "Teach how to correctly use a, an and the.",
        "topics": ["A", "An", "The", "No article"],
    },
    {
        "lesson": 8,
        "title": "Prepositions",
        "module": "Grammar Accuracy",
        "objective": "Teach common English prepositions and their correct usage.",
        "topics": ["In", "On", "At", "To", "For", "From"],
    },
    {
        "lesson": 9,
        "title": "Modal Verbs",
        "module": "Grammar Accuracy",
        "objective": "Teach common modal verbs naturally.",
        "topics": ["Can", "Could", "Should", "Must", "Might"],
    },
    {
        "lesson": 10,
        "title": "Adjectives and Adverbs",
        "module": "Vocabulary and Grammar",
        "objective": "Teach how to describe people, things and actions accurately.",
        "topics": ["Adjectives", "Adverbs", "Word position", "Common mistakes"],
    },
    {
        "lesson": 11,
        "title": "Comparatives and Superlatives",
        "module": "Grammar Development",
        "objective": "Teach how to compare people, objects and situations.",
        "topics": ["Comparatives", "Superlatives", "More", "Most", "Irregular forms"],
    },
    {
        "lesson": 12,
        "title": "Present Perfect",
        "module": "Advanced Tenses",
        "objective": "Teach how to use the present perfect for experiences and recent events.",
        "topics": ["Have/has", "Past participles", "Ever", "Never", "Already", "Yet"],
    },
    {
        "lesson": 13,
        "title": "Conditionals",
        "module": "Advanced Grammar",
        "objective": "Teach real, possible and hypothetical situations.",
        "topics": ["Zero conditional", "First conditional", "Second conditional"],
    },
    {
        "lesson": 14,
        "title": "Reported Speech",
        "module": "Advanced Grammar",
        "objective": "Teach how to report what another person has said.",
        "topics": ["Direct speech", "Reported speech", "Tense changes", "Pronoun changes"],
    },
    {
        "lesson": 15,
        "title": "Vocabulary Development",
        "module": "Vocabulary",
        "objective": "Improve vocabulary and the ability to use new words naturally.",
        "topics": ["Synonyms", "Antonyms", "Context", "Word choice", "Collocations"],
    },
    {
        "lesson": 16,
        "title": "British English Pronunciation",
        "module": "Pronunciation",
        "objective": "Improve British English pronunciation and clarity.",
        "topics": ["TH sounds", "Vowels", "Word stress", "Sentence stress", "Connected speech"],
    },
    {
        "lesson": 17,
        "title": "Conversation Skills",
        "module": "Speaking",
        "objective": "Develop natural everyday English conversation skills.",
        "topics": [
            "Starting conversations",
            "Asking questions",
            "Responding naturally",
            "Follow-up questions",
        ],
    },
    {
        "lesson": 18,
        "title": "Professional English",
        "module": "Professional English",
        "objective": "Teach English for workplace and professional situations.",
        "topics": ["Meetings", "Emails", "Presentations", "Professional vocabulary"],
    },
    {
        "lesson": 19,
        "title": "Reading and Comprehension",
        "module": "Reading",
        "objective": "Improve the ability to understand written English.",
        "topics": ["Main ideas", "Details", "Inference", "Vocabulary from context"],
    },
    {
        "lesson": 20,
        "title": "Writing",
        "module": "Writing",
        "objective": "Improve the ability to write clear and grammatically correct English.",
        "topics": ["Paragraph structure", "Grammar", "Vocabulary", "Punctuation", "Professional writing"],
    },
    {
        "lesson": 21,
        "title": "Listening",
        "module": "Listening",
        "objective": "Improve the ability to understand spoken English.",
        "topics": [
            "Listening comprehension",
            "Speaking speed",
            "Key information",
            "British English expressions",
        ],
    },
    {
        "lesson": 22,
        "title": "Final English Assessment",
        "module": "Assessment",
        "objective": "Assess overall progress across the curriculum.",
        "topics": [
            "Speaking",
            "Grammar",
            "Vocabulary",
            "Pronunciation",
            "Reading",
            "Writing",
            "Listening",
        ],
    },
]

_DATA_PATH = Path(os.getenv("ENGLISH_PROGRESS_PATH", Path(__file__).parent / "data" / "english_progress.json"))
_LOCK = threading.Lock()
_store: dict[str, dict[str, Any]] | None = None


def lesson_for(number: int) -> dict[str, Any]:
    current = max(1, min(int(number or 1), CURRICULUM_TOTAL_LESSONS))
    return next((item for item in CURRICULUM if item["lesson"] == current), CURRICULUM[0])


def _default_student(student_id: str) -> dict[str, Any]:
    name = "John" if student_id.lower() == DEFAULT_STUDENT_ID else student_id.replace("-", " ").title()
    return {
        "student_id": student_id,
        "name": name,
        "level": "A2",
        "current_lesson": 1,
        "overall_progress": 0,
        "completed_lessons": [],
        "strengths": [],
        "weaknesses": [],
        "recent_mistakes": [],
        "vocabulary": [],
        "grammar_scores": {},
        "teacher_summary": "No previous teacher summary available.",
        "lesson_history": [],
    }


def _load_store() -> dict[str, dict[str, Any]]:
    global _store
    if _store is not None:
        return _store
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _DATA_PATH.exists():
        try:
            raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _store = {str(key): value for key, value in raw.items() if isinstance(value, dict)}
                return _store
        except (OSError, json.JSONDecodeError):
            pass
    _store = {DEFAULT_STUDENT_ID: _default_student(DEFAULT_STUDENT_ID)}
    _persist()
    return _store


def _persist() -> None:
    if _store is None:
        return
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(json.dumps(_store, indent=2), encoding="utf-8")


def get_student(student_id: str | None) -> dict[str, Any]:
    sid = (student_id or DEFAULT_STUDENT_ID).strip() or DEFAULT_STUDENT_ID
    with _LOCK:
        store = _load_store()
        if sid not in store:
            store[sid] = _default_student(sid)
            _persist()
        return json.loads(json.dumps(store[sid]))


def build_lesson_response(student_id: str | None = None) -> dict[str, Any]:
    student = get_student(student_id)
    current_lesson = int(student.get("current_lesson") or 1)
    lesson = lesson_for(current_lesson)
    return {
        "student_id": student.get("student_id") or DEFAULT_STUDENT_ID,
        "student_name": student.get("name") or "John",
        "level": student.get("level") or "A2",
        "current_lesson": current_lesson,
        "overall_progress": int(student.get("overall_progress") or 0),
        "completed_lessons": student.get("completed_lessons") or [],
        "strengths": student.get("strengths") or [],
        "weaknesses": student.get("weaknesses") or [],
        "recent_mistakes": student.get("recent_mistakes") or [],
        "vocabulary": student.get("vocabulary") or [],
        "grammar_scores": student.get("grammar_scores") or {},
        "teacher_summary": student.get("teacher_summary")
        or "No previous teacher summary available.",
        "lesson_history": student.get("lesson_history") or [],
        "current_lesson_details": lesson,
        "curriculum_total_lessons": CURRICULUM_TOTAL_LESSONS,
    }


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        return [part for part in parts if part]
    return [value]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def process_lesson_progress(body: dict[str, Any]) -> dict[str, Any]:
    student_id = str(body.get("student_id") or DEFAULT_STUDENT_ID)
    lesson_number = max(1, min(_as_int(body.get("lesson_number"), 1), CURRICULUM_TOTAL_LESSONS))
    score = max(0, min(100, _as_int(body.get("score"), 0)))
    lesson_completed = body.get("lesson_completed") is True or str(
        body.get("lesson_completed")
    ).lower() in {"true", "1", "yes"}
    passed = lesson_completed and score >= PASS_SCORE

    next_lesson = lesson_number
    if passed and lesson_number < CURRICULUM_TOTAL_LESSONS:
        next_lesson = lesson_number + 1
    if lesson_number >= CURRICULUM_TOTAL_LESSONS and passed:
        next_lesson = CURRICULUM_TOTAL_LESSONS

    overall_progress = round(((next_lesson - 1) / CURRICULUM_TOTAL_LESSONS) * 100)

    return {
        "student_id": student_id,
        "lesson_number": lesson_number,
        "lesson_completed": lesson_completed,
        "current_lesson": next_lesson,
        "score": score,
        "passed": passed,
        "next_lesson": next_lesson,
        "overall_progress": overall_progress,
        "strengths": _as_list(body.get("strengths")),
        "weaknesses": _as_list(body.get("weaknesses")),
        "mistakes": _as_list(body.get("mistakes")),
        "new_vocabulary": _as_list(body.get("new_vocabulary")),
        "grammar_scores": body.get("grammar_scores") if isinstance(body.get("grammar_scores"), dict) else {},
        "teacher_summary": str(body.get("teacher_summary") or ""),
        "recommended_next_step": str(body.get("recommended_next_step") or ""),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _unique_extend(existing: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item) for item in existing}
    merged = list(existing)
    for item in incoming:
        key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def save_progress(payload: dict[str, Any]) -> dict[str, Any]:
    processed = process_lesson_progress(payload)
    student_id = processed["student_id"]
    with _LOCK:
        store = _load_store()
        student = store.get(student_id) or _default_student(student_id)
        student["student_id"] = student_id
        student["current_lesson"] = processed["current_lesson"]
        student["overall_progress"] = processed["overall_progress"]
        if processed["passed"]:
            completed = list(student.get("completed_lessons") or [])
            if processed["lesson_number"] not in completed:
                completed.append(processed["lesson_number"])
            student["completed_lessons"] = completed
        student["strengths"] = _unique_extend(student.get("strengths") or [], processed["strengths"])
        student["weaknesses"] = processed["weaknesses"] or student.get("weaknesses") or []
        student["recent_mistakes"] = processed["mistakes"] or student.get("recent_mistakes") or []
        student["vocabulary"] = _unique_extend(
            student.get("vocabulary") or [], processed["new_vocabulary"]
        )
        grammar = dict(student.get("grammar_scores") or {})
        grammar.update(processed["grammar_scores"] or {})
        student["grammar_scores"] = grammar
        if processed["teacher_summary"]:
            student["teacher_summary"] = processed["teacher_summary"]
        history = list(student.get("lesson_history") or [])
        history.append(
            {
                "lesson_number": processed["lesson_number"],
                "score": processed["score"],
                "passed": processed["passed"],
                "teacher_summary": processed["teacher_summary"],
                "recommended_next_step": processed["recommended_next_step"],
                "completed_at": processed["completed_at"],
            }
        )
        student["lesson_history"] = history[-50:]
        store[student_id] = student
        _persist()

    return {
        "success": True,
        "student_id": processed["student_id"],
        "lesson_number": processed["lesson_number"],
        "lesson_completed": processed["lesson_completed"],
        "score": processed["score"],
        "passed": processed["passed"],
        "current_lesson": processed["current_lesson"],
        "next_lesson": processed["next_lesson"],
        "overall_progress": processed["overall_progress"],
        "message": (
            "Progress submitted successfully. The next lesson should be available if the API saved the updated current_lesson."
            if processed["passed"]
            else "Progress submitted. Additional practice is recommended before progressing."
        ),
        "api_response": {"success": True, "student": get_student(student_id)},
    }


def extract_student_id(payload: dict[str, Any] | None, query: dict[str, Any] | None = None) -> str:
    query = query or {}
    body = payload or {}
    nested_query = body.get("query") if isinstance(body.get("query"), dict) else {}
    student = body.get("student") if isinstance(body.get("student"), dict) else {}
    return str(
        query.get("student_id")
        or nested_query.get("student_id")
        or body.get("student_id")
        or student.get("student_id")
        or DEFAULT_STUDENT_ID
    )
