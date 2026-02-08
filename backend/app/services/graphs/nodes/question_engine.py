"""
Question Engine Node

Generates interview questions using LangChain structured output.
Responsibilities:
- Generate initial questions for pillars
- Generate follow-up questions
- Adapt difficulty based on state signals
- Maintain conversation context

Uses structured output (Pydantic schemas) - no manual parsing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from app.core.llm import get_llm
from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    RouterDecision,
    log_transition,
    get_current_pillar,
    get_conversation_context,
)
from app.schemas.outputs.question_outputs import (
    QuestionGenerationOutput,
    FollowUpQuestionOutput,
)
from app.prompts import (
    QUESTION_GENERATION_PROMPT,
    FOLLOW_UP_QUESTION_PROMPT,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def question_engine_node(state: InterviewState) -> Dict[str, Any]:
    """
    Generate the next interview question.

    This node generates:
    - Initial questions when starting a pillar
    - Follow-up questions when router decides FOLLOW_UP
    - Next questions when router decides CONTINUE_PILLAR

    Args:
        state: Current interview state

    Returns:
        State updates with new question
    """
    router_decision = state.get("router_decision", RouterDecision.CONTINUE_PILLAR.value)
    current_phase = state.get("phase", InterviewPhase.QUESTIONING.value)

    # Don't generate if interview is ending
    if current_phase in [InterviewPhase.COMPLETED.value, InterviewPhase.TERMINATED.value]:
        logger.info("Interview ended, skipping question generation")
        return {}

    logger.info(f"Question engine: decision={router_decision}")

    try:
        if router_decision == RouterDecision.FOLLOW_UP.value:
            question_output = await _generate_follow_up(state)
            is_follow_up = True
        else:
            question_output = await _generate_new_question(state)
            is_follow_up = False

        # Create question record
        question_id = str(uuid.uuid4())
        current_pillar = get_current_pillar(state)
        pillar_name = current_pillar.get("skill", "Unknown") if current_pillar else "Unknown"

        question_record = {
            "question_id": question_id,
            "pillar_index": state.get("current_pillar_index", 0),
            "pillar_name": pillar_name,
            "question_text": question_output.question if hasattr(question_output, 'question') else question_output.follow_up_question,
            "question_depth": state.get("current_question_depth", 1),
            "is_follow_up": is_follow_up,
            "question_sent_at": datetime.utcnow().isoformat(),
            "answer_text": None,
            "answer_audio_url": None,
            "answer_received_at": None,
            "reading_time_used": None,
            "answer_time_used": None,
            "evaluation_signals": None,
        }

        # Update question records
        existing_records = state.get("question_records", [])
        updated_records = existing_records + [question_record]

        # Update message history
        question_text = question_record["question_text"]
        message_history = [AIMessage(content=question_text)]

        # Update counters
        questions_in_pillar = state.get("questions_in_current_pillar", 0)
        follow_ups_in_pillar = state.get("follow_ups_in_current_pillar", 0)
        total_questions = state.get("total_questions_asked", 0)
        total_follow_ups = state.get("total_follow_ups", 0)

        if is_follow_up:
            follow_ups_in_pillar += 1
            total_follow_ups += 1
        else:
            questions_in_pillar += 1
            total_questions += 1

        # Update focus areas with question count
        focus_areas = state.get("focus_areas", [])
        current_idx = state.get("current_pillar_index", 0)
        if current_idx < len(focus_areas):
            updated_focus_areas = focus_areas.copy()
            pillar = updated_focus_areas[current_idx].copy()
            pillar["questions_asked"] = pillar.get("questions_asked", 0) + 1
            if is_follow_up:
                pillar["follow_ups_used"] = pillar.get("follow_ups_used", 0) + 1
            updated_focus_areas[current_idx] = pillar
        else:
            updated_focus_areas = focus_areas

        updates = {
            "current_question_id": question_id,
            "current_question": question_text,
            "awaiting_answer": True,
            "question_records": updated_records,
            "message_history": message_history,  # Annotated list will append
            "questions_in_current_pillar": questions_in_pillar,
            "follow_ups_in_current_pillar": follow_ups_in_pillar,
            "total_questions_asked": total_questions,
            "total_follow_ups": total_follow_ups,
            "focus_areas": updated_focus_areas,
            "phase": InterviewPhase.AWAITING_ANSWER.value,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Set timing for answer window
        timing = state.get("timing", {}).copy()
        now = datetime.utcnow()
        timing["question_displayed_at"] = now.isoformat()
        reading_buffer = timing.get("reading_buffer_seconds", 20)
        answer_window = timing.get("answer_window_seconds", 45)

        from datetime import timedelta
        timing["reading_deadline"] = (now + timedelta(seconds=reading_buffer)).isoformat()
        timing["answer_deadline"] = (now + timedelta(seconds=reading_buffer + answer_window)).isoformat()

        updates["timing"] = timing

        # logger.info(
        #     f"Generated question: {question_text[:50]}... "
        #     f"(pillar={pillar_name}, depth={state.get('current_question_depth', 1)}, "
        #     f"follow_up={is_follow_up})"
        # )

        return updates

    except Exception as e:
        logger.error(f"Question generation failed: {e}", exc_info=True)
        error_count = state.get("error_count", 0) + 1
        
        # Emergency Fallback - ALWAYS return a question to prevent stuck state
        safe_year = datetime.now().year
        fallback_question = (
            f"Could you tell me more about your recent projects and the technologies you used? "
            f"I'm interested in your experience."
        )
        
        # Create a valid state update even on error
        question_id = str(uuid.uuid4())
        question_record = {
            "question_id": question_id,
            "pillar_index": state.get("current_pillar_index", 0),
            "pillar_name": "General (Fallback)",
            "question_text": fallback_question,
            "question_depth": 1,
            "is_follow_up": False,
            "question_sent_at": datetime.utcnow().isoformat(),
            "answer_text": None,
            "answer_audio_url": None,
            "answer_received_at": None,
        }
        
        # Force these updates alongside error info
        updated_records = state.get("question_records", []) + [question_record]
        message_history = [AIMessage(content=fallback_question)]
        
        timing = state.get("timing", {}).copy()
        now = datetime.utcnow()
        timing["question_displayed_at"] = now.isoformat()
        timing["reading_deadline"] = (now + timedelta(seconds=20)).isoformat()
        timing["answer_deadline"] = (now + timedelta(seconds=65)).isoformat()

        return {
            "error_count": error_count,
            "last_error": str(e),
            "updated_at": now.isoformat(),
            
            # Critical: Ensure flow continues
            "current_question_id": question_id,
            "current_question": fallback_question,
            "awaiting_answer": True,
            "question_records": updated_records,
            "message_history": message_history,
            "phase": InterviewPhase.AWAITING_ANSWER.value,
            "timing": timing,
        }


async def _generate_new_question(state: InterviewState) -> QuestionGenerationOutput:
    """Generate a new question using structured output."""
    current_pillar = get_current_pillar(state)
    pillar_name = current_pillar.get("skill", "General") if current_pillar else "General"
    pillar_reason = current_pillar.get("reason", "") if current_pillar else ""

    depth_level = state.get("current_question_depth", 1)
    job_role = state.get("job_role", "Software Engineer")
    resume_context = state.get("resume_context", "")[:1000]  # Truncate for context window

    # Get conversation context
    conversation = get_conversation_context(state, max_messages=6)
    conversation_str = "\n".join([
        f"{'Assistant' if c['role'] == 'assistant' else 'Candidate'}: {c['content'][:200]}"
        for c in conversation
    ]) if conversation else "No previous conversation."

    # Get topics already covered in this pillar
    question_records = state.get("question_records", [])
    current_pillar_idx = state.get("current_pillar_index", 0)
    covered_topics = [
        r.get("question_text", "")[:100]
        for r in question_records
        if r.get("pillar_index") == current_pillar_idx
    ]
    previous_topics = "\n".join(covered_topics) if covered_topics else "None yet."

    # Build prompt inputs
    prompt_inputs = {
        "pillar_name": pillar_name,
        "pillar_reason": pillar_reason,
        "depth_level": depth_level,
        "job_role": job_role,
        "resume_context": f"Resume highlights:\n{resume_context}" if resume_context else "No resume context available.",
        "conversation_context": conversation_str,
        "previous_topics_covered": previous_topics,
        "avoid_concepts": "",
    }

    # Get LLM with structured output
    llm = get_llm()
    structured_llm = llm.with_structured_output(QuestionGenerationOutput)

    try:
        # Use invoke to handle messages properly
        formatted_prompt = QUESTION_GENERATION_PROMPT.invoke(prompt_inputs)
        result = await structured_llm.ainvoke(formatted_prompt)
        return result
    except Exception as e:
        logger.error(f"LLM generation failed: {e}", exc_info=True)
        
        # Dynamic Recovery: Ask LLM for a plain string question
        try:
            recovery_prompt = (
                f"You are an interviewer. Generate one clear, technical interview question "
                f"about '{pillar_name}' for a '{job_role}'. "
                f"Return ONLY the question text, no other text."
            )
            recovery_response = await llm.ainvoke(recovery_prompt)
            question_text = recovery_response.content.strip()
            
            return QuestionGenerationOutput(
                question=question_text,
                question_type="practical",
                depth_level=depth_level,
                target_skill=pillar_name,
                expected_coverage=["Core concepts", "Practical application"],
                time_estimate_seconds=45,
                probing_intent="Dynamic recovery generation"
            )
        except Exception as e2:
            # Ultimate safety net if even recovery fails
            logger.error(f"Recovery generation failed: {e2}")
            return QuestionGenerationOutput(
                question=f"Could you describe your experience with {pillar_name} in detail?",
                question_type="practical",
                depth_level=depth_level,
                target_skill=pillar_name,
                expected_coverage=["Experience"],
                time_estimate_seconds=45,
                probing_intent="Static fallback"
            )


async def _generate_follow_up(state: InterviewState) -> FollowUpQuestionOutput:
    """Generate a follow-up question using structured output."""
    current_pillar = get_current_pillar(state)
    pillar_name = current_pillar.get("skill", "General") if current_pillar else "General"

    # Get the last question and answer
    question_records = state.get("question_records", [])
    if not question_records:
        # Fallback to new question if no records
        new_q = await _generate_new_question(state)
        return FollowUpQuestionOutput(
            follow_up_question=new_q.question,
            builds_on="Previous context",
            gap_addressed="General exploration",
            expected_elaboration=[],
        )

    last_record = question_records[-1]
    original_question = last_record.get("question_text", "")
    candidate_answer = last_record.get("answer_text", "")

    # Get analysis signals for probe areas
    signals = state.get("last_analysis_signals", {})
    probe_areas = signals.get("suggested_probe_areas", [])
    missing_concepts = signals.get("missing_concepts", [])

    probe_area = probe_areas[0] if probe_areas else (
        missing_concepts[0] if missing_concepts else "deeper understanding"
    )

    # Build prompt inputs
    prompt_inputs = {
        "original_question": original_question,
        "candidate_answer": candidate_answer or "No answer provided",
        "probe_area": probe_area,
        "pillar_name": pillar_name,
        "follow_up_reason": signals.get("analysis_summary", ""),
        "gaps_identified": ", ".join(missing_concepts) if missing_concepts else "None identified",
    }

    # Get LLM with structured output
    llm = get_llm()
    structured_llm = llm.with_structured_output(FollowUpQuestionOutput)

    try:
        # Use invoke to handle messages properly
        formatted_prompt = FOLLOW_UP_QUESTION_PROMPT.invoke(prompt_inputs)
        result = await structured_llm.ainvoke(formatted_prompt)
        return result
    except Exception as e:
        logger.error(f"Follow-up generation failed: {e}", exc_info=True)
        
        # Dynamic Recovery for Follow-up
        try:
            recovery_prompt = (
                f"Generate a short follow-up interview question about '{pillar_name}'. "
                f"The candidate just discussed this topic. Ask for more specific details. "
                f"Return ONLY the question text."
            )
            recovery_response = await llm.ainvoke(recovery_prompt)
            question_text = recovery_response.content.strip()

            return FollowUpQuestionOutput(
                follow_up_question=question_text,
                builds_on="Previous answer",
                gap_addressed="Depth",
                expected_elaboration=["Specific details"]
            )
        except Exception as e2:
            logger.error(f"Recovery follow-up failed: {e2}")
            return FollowUpQuestionOutput(
                follow_up_question=f"Can you provide more specific examples regarding {pillar_name}?",
                builds_on="Previous answer",
                gap_addressed="Examples",
                expected_elaboration=["Examples"]
            )


def adjust_difficulty(state: InterviewState, adjustment: int) -> Dict[str, Any]:
    """
    Adjust question difficulty based on performance.

    Args:
        state: Current interview state
        adjustment: -1 (decrease), 0 (maintain), +1 (increase)

    Returns:
        State update with new difficulty
    """
    current_depth = state.get("current_question_depth", 1)
    new_depth = max(1, min(5, current_depth + adjustment))

    if new_depth != current_depth:
        logger.info(f"Adjusting difficulty: {current_depth} -> {new_depth}")

    return {"current_question_depth": new_depth}
