"""
Tests for user_model.py
Run: python mezo-training/tests/test_user_model.py
"""

import sys
import os
import asyncio
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.auto_learning.user_model import UserModel, Observation


def make_model():
    tmpdir = tempfile.mkdtemp()
    return UserModel(db_dir=tmpdir), tmpdir


async def test_observe_creates_fact():
    model, tmpdir = make_model()
    try:
        obs = Observation("tool_run", "git status")
        fact = await model.observe("u1", obs)
        assert fact is not None
        assert fact.category == "workflow"
        assert fact.content == "git status"
        assert fact.user_id == "u1"
        print("[OK] test_observe_creates_fact")
    finally:
        shutil.rmtree(tmpdir)


async def test_sensitive_content_tagged():
    model, tmpdir = make_model()
    try:
        obs = Observation("explicit_feedback", "I am dealing with health anxiety")
        fact = await model.observe("u1", obs)
        assert fact is not None
        assert fact.category == "sensitive", f"Expected sensitive, got: {fact.category}"
        print("[OK] test_sensitive_content_tagged")
    finally:
        shutil.rmtree(tmpdir)


async def test_sensitive_excluded_from_retrieval():
    model, tmpdir = make_model()
    try:
        await model.observe("u1", Observation("tool_run", "git status"))
        await model.observe("u1", Observation("explicit_feedback", "I have depression"))

        # Normal retrieval should NOT include sensitive facts
        facts = await model.get_relevant_context("u1")
        categories = [f["category"] for f in facts]
        assert "sensitive" not in categories, f"Sensitive should not appear: {categories}"
        assert any(c == "workflow" for c in categories)
        print("[OK] test_sensitive_excluded_from_retrieval")
    finally:
        shutil.rmtree(tmpdir)


async def test_sensitive_visible_with_flag():
    model, tmpdir = make_model()
    try:
        await model.observe("u1", Observation("explicit_feedback", "I have a mortgage"))
        facts = await model.get_all_facts("u1", include_sensitive=True)
        categories = [f["category"] for f in facts]
        assert "sensitive" in categories
        print("[OK] test_sensitive_visible_with_flag")
    finally:
        shutil.rmtree(tmpdir)


async def test_deduplication():
    model, tmpdir = make_model()
    try:
        obs = Observation("tool_run", "npm test")
        f1 = await model.observe("u1", obs)
        f2 = await model.observe("u1", obs)  # duplicate
        assert f1 is not None
        assert f2 is None, "Duplicate observation should not create a new fact"

        facts = await model.get_all_facts("u1")
        npm_facts = [f for f in facts if f["content"] == "npm test"]
        assert len(npm_facts) == 1, f"Expected 1 fact, got {len(npm_facts)}"
        print("[OK] test_deduplication")
    finally:
        shutil.rmtree(tmpdir)


async def test_delete_fact():
    model, tmpdir = make_model()
    try:
        fact = await model.observe("u1", Observation("tool_run", "pip list"))
        assert fact is not None
        fact_id = fact.id

        deleted = await model.delete_fact("u1", fact_id)
        assert deleted

        facts = await model.get_all_facts("u1")
        active_ids = [f["id"] for f in facts]
        assert fact_id not in active_ids, "Deleted fact should not appear in get_all_facts"
        print("[OK] test_delete_fact")
    finally:
        shutil.rmtree(tmpdir)


async def test_wipe_model():
    model, tmpdir = make_model()
    try:
        await model.observe("u1", Observation("tool_run", "git status"))
        await model.observe("u1", Observation("preference", "prefers Python"))
        await model.observe("u1", Observation("tool_run", "pytest"))

        wiped = await model.wipe_model("u1")
        assert wiped == 3

        facts = await model.get_all_facts("u1")
        assert len(facts) == 0, f"After wipe, expected 0 facts, got {len(facts)}"
        print("[OK] test_wipe_model")
    finally:
        shutil.rmtree(tmpdir)


async def test_multi_user_isolation():
    model, tmpdir = make_model()
    try:
        await model.observe("u1", Observation("tool_run", "git status"))
        await model.observe("u2", Observation("tool_run", "docker ps"))

        u1_facts = await model.get_all_facts("u1")
        u2_facts = await model.get_all_facts("u2")

        u1_contents = [f["content"] for f in u1_facts]
        u2_contents = [f["content"] for f in u2_facts]

        assert "git status" in u1_contents and "docker ps" not in u1_contents
        assert "docker ps" in u2_contents and "git status" not in u2_contents
        print("[OK] test_multi_user_isolation")
    finally:
        shutil.rmtree(tmpdir)


async def test_relevant_context_priority():
    model, tmpdir = make_model()
    try:
        await model.observe("u1", Observation("explicit_feedback", "prefers concise answers"))
        await model.observe("u1", Observation("tool_run", "pytest --cov"))
        await model.observe("u1", Observation("tool_run", "git status"))

        facts = await model.get_relevant_context("u1")
        categories = [f["category"] for f in facts]

        # Workflow facts should come before preference facts
        if "workflow" in categories and "preference" in categories:
            assert categories.index("workflow") < categories.index("preference"), \
                "Workflow facts should have higher priority than preference facts"
        print("[OK] test_relevant_context_priority")
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        test_observe_creates_fact,
        test_sensitive_content_tagged,
        test_sensitive_excluded_from_retrieval,
        test_sensitive_visible_with_flag,
        test_deduplication,
        test_delete_fact,
        test_wipe_model,
        test_multi_user_isolation,
        test_relevant_context_priority,
    ]
    for t in tests:
        asyncio.run(t())
    print(f"\n[PASS] All {len(tests)} user_model tests passed!")
