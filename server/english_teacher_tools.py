"""Pipecat LLM tools that call the same English-teacher logic as the webhooks."""

from __future__ import annotations

from typing import Any

from english_teacher import build_lesson_response, save_progress


async def get_student_lesson(params: Any, student_id: str = "john") -> None:
    """Load this student's current British English lesson and progress.

    Call this at the start of a session, and whenever you need the student's
    level, strengths, weaknesses, or current lesson details.

    Args:
        student_id: The student identifier. Use john if the student has not given another id.
    """
    await params.result_callback(build_lesson_response(student_id))


async def save_lesson_progress(
    params: Any,
    student_id: str = "john",
    lesson_number: int = 1,
    score: int = 0,
    lesson_completed: bool = False,
    strengths: str = "",
    weaknesses: str = "",
    mistakes: str = "",
    new_vocabulary: str = "",
    teacher_summary: str = "",
    recommended_next_step: str = "",
) -> None:
    """Save lesson results after teaching or assessing the student.

    Use this at the end of a lesson. A completed lesson with a score of 70 or
    more unlocks the next lesson.

    Args:
        student_id: The student identifier.
        lesson_number: The lesson that was just taught, from 1 to 22.
        score: Overall lesson score from 0 to 100.
        lesson_completed: True if the lesson was finished, not just started.
        strengths: Comma-separated strengths you noticed.
        weaknesses: Comma-separated areas that still need work.
        mistakes: Comma-separated example mistakes from this lesson.
        new_vocabulary: Comma-separated new words or phrases taught.
        teacher_summary: Short summary of what happened in the lesson.
        recommended_next_step: What the student should practise next.
    """
    result = save_progress(
        {
            "student_id": student_id,
            "lesson_number": lesson_number,
            "score": score,
            "lesson_completed": lesson_completed,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "mistakes": mistakes,
            "new_vocabulary": new_vocabulary,
            "teacher_summary": teacher_summary,
            "recommended_next_step": recommended_next_step,
        }
    )
    await params.result_callback(result)


ENGLISH_TEACHER_TOOLS = [get_student_lesson, save_lesson_progress]
