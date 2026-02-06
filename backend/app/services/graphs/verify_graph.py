import asyncio
import uuid
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from unittest.mock import patch, MagicMock

# Import the graph builder
from app.services.graphs.interview_orchestration import build_interview_graph, get_initial_state

@patch('app.services.graphs.interview_orchestration.get_llm')
async def run_verification(mock_get_llm):
    print("🚀 Starting Graph Verification...")

from langchain_core.runnables import Runnable, RunnableConfig
from typing import Optional, Any

class MockRunnable(Runnable):
    def invoke(self, input: Any, config: Optional[RunnableConfig] = None, **kwargs: Any) -> Any:
        return self._generate_response(input)

    async def ainvoke(self, input: Any, config: Optional[RunnableConfig] = None, **kwargs: Any) -> Any:
        return self._generate_response(input)
    
    def _generate_response(self, input_val: Any) -> AIMessage:
        input_text = str(input_val)
        if "Python" in input_text or "messages" in input_text:
             return AIMessage(content="What are the key differences between a list and a tuple in Python?")
        
        if "answer" in input_text or "Candidate Answer" in input_text:
             return AIMessage(content='{"is_relevant": true, "correctness_score": 8, "depth_score": 3, "followup_suggested": false, "cheating_suspicion": 0}')
             
        return AIMessage(content="Mock Response")

@patch('app.services.graphs.interview_orchestration.get_llm')
async def run_verification(mock_get_llm):
    print("🚀 Starting Graph Verification...")

    # Configure Mock LLM
    mock_get_llm.return_value = MockRunnable()
    
    # Setup
    checkpointer = MemorySaver()
    graph = build_interview_graph(checkpointer=checkpointer)
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. Initialize State
    initial_state = get_initial_state()
    initial_state.update({
        "interview_id": "test-123",
        "job_role": "Senior Python Engineer",
        "resume_context": "Experienced in Django, FastAPI, and AWS.",
        "focus_areas": [
            {"skill": "Python Core", "description": "GIL, Decorators, Generators"},
            {"skill": "System Design", "description": "Scalability, DBs"}
        ]
    })
    
    print("\n[Step 1] Starting Interview...")
    async for event in graph.astream(initial_state, config):
        for key, value in event.items():
            print(f"  → Node: {key}")
            if key == "question_engine":
                print(f"    ❓ Question: {value.get('current_question')}")

    # Check state at interrupt
    state_snapshot = await graph.aget_state(config)
    print(f"\n[Paused] Next node: {state_snapshot.next}")
    
    if not state_snapshot.next:
        print("❌ Error: Graph finished unexpectedly!")
        return

    assert "audio_pipeline" in state_snapshot.next, f"Expected audio_pipeline, got {state_snapshot.next}"
    
    # 2. Simulate User Answer (Resume)
    print("\n[Step 2] User Answers 'I use asyncio for concurrency.'")
    
    resume_update = {
        "current_answer_text": "I use asyncio event loops to handle high concurrency with non-blocking I/O.",
        "router_decision": "resume" 
    }
    
    await graph.aupdate_state(config, resume_update)
    
    # Resume
    print("  → Resuming Graph...")
    async for event in graph.astream(None, config):
        for key, value in event.items():
            print(f"  → Node: {key}")
            if key == "decision_router":
                print(f"    🧠 Decision: {value.get('router_decision')}")
                
    # Check new state
    final_state = await graph.aget_state(config)
    ctx = final_state.values
    print(f"\n[Status] Current Depth: {ctx.get('current_question_depth')}")
    print(f"[Status] Q Count: {ctx.get('question_count_in_pillar')}")
    
    # 3. Simulate Loop
    print("\n[Step 3] Answering Second Question...")
    assert "audio_pipeline" in final_state.next
    
    resume_update_2 = {
        "current_answer_text": "Generators allow lazy evaluation."
    }
    await graph.aupdate_state(config, resume_update_2)
    
    async for event in graph.astream(None, config):
        for key, value in event.items():
             print(f"  → Node: {key}")
             
    print("\n✅ Verification Complete!")

if __name__ == "__main__":
    asyncio.run(run_verification())
