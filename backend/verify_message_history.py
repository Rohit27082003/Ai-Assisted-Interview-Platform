#!/usr/bin/env python3
"""
Verify Message History Tracking in Interview State

This script checks that the message history is properly maintained
with both AIMessage (questions) and HumanMessage (answers).

Usage:
    python verify_message_history.py
"""

import asyncio
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage

# Import state and utilities
from app.schemas.state import (
    InterviewState,
    create_initial_state,
    get_message_history_for_pillar,
)


def verify_message_history_structure(state: InterviewState) -> Dict[str, Any]:
    """
    Verify that message history is properly structured.

    Returns:
        Dict with verification results
    """
    message_history = state.get("message_history", [])

    results = {
        "total_messages": len(message_history),
        "ai_messages": 0,
        "human_messages": 0,
        "other_messages": 0,
        "alternating_pattern": True,
        "details": [],
    }

    # Count message types
    for i, msg in enumerate(message_history):
        if isinstance(msg, AIMessage):
            results["ai_messages"] += 1
            msg_type = "AI"
        elif isinstance(msg, HumanMessage):
            results["human_messages"] += 1
            msg_type = "Human"
        else:
            results["other_messages"] += 1
            msg_type = "Unknown"

        results["details"].append({
            "index": i,
            "type": msg_type,
            "content_preview": msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
        })

    # Check alternating pattern (AI -> Human -> AI -> Human)
    expected_pattern = True
    for i in range(len(message_history) - 1):
        current = message_history[i]
        next_msg = message_history[i + 1]

        if isinstance(current, AIMessage) and not isinstance(next_msg, HumanMessage):
            expected_pattern = False
            break
        elif isinstance(current, HumanMessage) and not isinstance(next_msg, AIMessage):
            expected_pattern = False
            break

    results["alternating_pattern"] = expected_pattern

    return results


def print_verification_results(results: Dict[str, Any]):
    """Print verification results in a readable format."""
    print("\n" + "=" * 60)
    print("MESSAGE HISTORY VERIFICATION RESULTS")
    print("=" * 60)

    print(f"\n📊 Message Counts:")
    print(f"  - Total Messages: {results['total_messages']}")
    print(f"  - AI Messages (Questions): {results['ai_messages']}")
    print(f"  - Human Messages (Answers): {results['human_messages']}")
    print(f"  - Other: {results['other_messages']}")

    print(f"\n🔄 Pattern Check:")
    if results["alternating_pattern"]:
        print("  ✅ Messages alternate correctly (AI -> Human -> AI -> Human)")
    else:
        print("  ❌ Messages do NOT alternate correctly")

    print(f"\n📝 Message Details:")
    for detail in results["details"]:
        icon = "🤖" if detail["type"] == "AI" else "👤" if detail["type"] == "Human" else "❓"
        print(f"  {detail['index']:2d}. {icon} {detail['type']:6s}: {detail['content_preview']}")

    # Validation checks
    print(f"\n✅ Validation:")
    checks = []

    if results["total_messages"] > 0:
        checks.append(("✅", "Message history exists"))
    else:
        checks.append(("❌", "Message history is empty"))

    if results["ai_messages"] > 0:
        checks.append(("✅", "AI messages (questions) present"))
    else:
        checks.append(("❌", "No AI messages found"))

    if results["human_messages"] > 0:
        checks.append(("✅", "Human messages (answers) present"))
    else:
        checks.append(("❌", "No Human messages found"))

    if results["alternating_pattern"]:
        checks.append(("✅", "Correct alternating pattern"))
    else:
        checks.append(("⚠️", "Pattern may be broken (check if interview just started)"))

    if results["other_messages"] == 0:
        checks.append(("✅", "No unexpected message types"))
    else:
        checks.append(("❌", f"Found {results['other_messages']} unexpected message types"))

    for status, message in checks:
        print(f"  {status} {message}")

    print("\n" + "=" * 60 + "\n")


async def test_message_history_with_mock_qa():
    """
    Test message history tracking with mock Q&A pairs.
    """
    print("🧪 Testing message history with mock interview data...")

    # Create initial state
    state = create_initial_state(
        interview_id="test-001",
        candidate_id="candidate-001",
        jd_id="jd-001",
        candidate_name="Test Candidate",
        candidate_email="test@example.com",
        job_role="Software Engineer",
        job_requirements={"skills": ["Python", "Angular"]},
        resume_context="Experienced developer with Python and Angular",
        focus_areas=[
            {"skill": "Python", "reason": "Core language"},
            {"skill": "Angular", "reason": "Frontend framework"}
        ]
    )

    print("✅ Initial state created")

    # Simulate Q&A pairs
    qa_pairs = [
        ("What is Python's GIL?", "The Global Interpreter Lock is a mutex that protects Python objects."),
        ("How does it affect multithreading?", "It prevents multiple threads from executing Python bytecode simultaneously."),
        ("What are alternatives to threading?", "We can use multiprocessing or asyncio for concurrency."),
    ]

    # Manually add messages (simulating what question_engine and audio_pipeline do)
    message_history = []

    for i, (question, answer) in enumerate(qa_pairs):
        # Add question (AIMessage)
        message_history.append(AIMessage(content=question))

        # Add answer (HumanMessage)
        message_history.append(HumanMessage(content=answer))

        print(f"  ✅ Added Q&A pair {i+1}")

    # Update state with message history
    state["message_history"] = message_history

    # Verify
    results = verify_message_history_structure(state)
    print_verification_results(results)

    # Test pillar-specific extraction
    print("🔍 Testing pillar-specific message extraction...")
    state["question_records"] = [
        {
            "question_id": "q1",
            "pillar_index": 0,
            "question_text": qa_pairs[0][0],
            "answer_text": qa_pairs[0][1],
        },
        {
            "question_id": "q2",
            "pillar_index": 0,
            "question_text": qa_pairs[1][0],
            "answer_text": qa_pairs[1][1],
        },
        {
            "question_id": "q3",
            "pillar_index": 1,  # Different pillar
            "question_text": qa_pairs[2][0],
            "answer_text": qa_pairs[2][1],
        },
    ]

    pillar_0_messages = get_message_history_for_pillar(state, 0)
    print(f"  ✅ Pillar 0 has {len(pillar_0_messages)} messages (expected: 4)")

    pillar_1_messages = get_message_history_for_pillar(state, 1)
    print(f"  ✅ Pillar 1 has {len(pillar_1_messages)} messages (expected: 2)")

    return results


def main():
    """Main entry point."""
    print("\n🚀 Message History Verification Tool")
    print("=" * 60)

    asyncio.run(test_message_history_with_mock_qa())

    print("\n📚 How to Use with Real Interview:")
    print("  1. Start an interview session")
    print("  2. After a few Q&A exchanges, access the state")
    print("  3. Run: verify_message_history_structure(state)")
    print("  4. Check that AI and Human messages alternate correctly")


if __name__ == "__main__":
    main()
