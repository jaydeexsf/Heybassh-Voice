"""Tests for British English teacher progress and webhook payloads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import english_teacher as et


class EnglishTeacherLogicTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = et._DATA_PATH
        self._orig_store = et._store
        et._DATA_PATH = Path(self._tmpdir.name) / "progress.json"
        et._store = None

    def tearDown(self) -> None:
        et._DATA_PATH = self._orig_path
        et._store = self._orig_store
        self._tmpdir.cleanup()

    def test_default_student_starts_on_lesson_one(self) -> None:
        lesson = et.build_lesson_response("john")
        self.assertEqual(lesson["student_id"], "john")
        self.assertEqual(lesson["current_lesson"], 1)
        self.assertEqual(lesson["current_lesson_details"]["title"], "Initial English Assessment")
        self.assertEqual(lesson["curriculum_total_lessons"], 22)

    def test_score_below_seventy_does_not_advance(self) -> None:
        result = et.save_progress(
            {
                "student_id": "john",
                "lesson_number": 1,
                "score": 65,
                "lesson_completed": True,
                "teacher_summary": "Needs more speaking practice.",
            }
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["current_lesson"], 1)
        self.assertEqual(et.get_student("john")["current_lesson"], 1)

    def test_passing_score_unlocks_next_lesson(self) -> None:
        result = et.save_progress(
            {
                "student_id": "john",
                "lesson_number": 1,
                "score": 82,
                "lesson_completed": True,
                "strengths": ["confidence"],
                "new_vocabulary": ["brilliant", "cheers"],
                "teacher_summary": "Strong first assessment.",
            }
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["current_lesson"], 2)
        self.assertEqual(result["overall_progress"], 5)
        student = et.get_student("john")
        self.assertEqual(student["current_lesson"], 2)
        self.assertIn(1, student["completed_lessons"])
        self.assertIn("brilliant", student["vocabulary"])

        lesson = et.build_lesson_response("john")
        self.assertEqual(lesson["current_lesson_details"]["title"], "Sentence Structure")

    def test_final_lesson_stays_at_twenty_two(self) -> None:
        result = et.process_lesson_progress(
            {
                "student_id": "john",
                "lesson_number": 22,
                "score": 90,
                "lesson_completed": True,
            }
        )
        self.assertEqual(result["next_lesson"], 22)
        self.assertEqual(result["overall_progress"], 95)

    def test_webhooks_load_and_save_progress(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from english_teacher_api import register_english_teacher_routes

        app = FastAPI()
        register_english_teacher_routes(app)
        client = TestClient(app)

        lesson = client.get(
            "/webhook/english-teacher/student-lesson",
            params={"student_id": "john"},
        )
        self.assertEqual(lesson.status_code, 200)
        self.assertEqual(lesson.json()["current_lesson"], 1)
        self.assertEqual(
            lesson.json()["current_lesson_details"]["title"],
            "Initial English Assessment",
        )

        saved = client.post(
            "/webhook/english-teacher/update-progress",
            json={
                "student_id": "john",
                "lesson_number": 1,
                "score": 80,
                "lesson_completed": True,
                "strengths": ["speaking"],
                "teacher_summary": "Passed the assessment.",
            },
        )
        self.assertEqual(saved.status_code, 200)
        body = saved.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["passed"])
        self.assertEqual(body["current_lesson"], 2)

        progress = client.get("/api/students/john/english-progress")
        self.assertEqual(progress.json()["current_lesson"], 2)


if __name__ == "__main__":
    unittest.main()
