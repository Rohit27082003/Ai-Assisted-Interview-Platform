
import asyncio
import sys
import os

# Add backend to sys.path
sys.path.append(os.getcwd())

from app.api.routes.interview_routes import _run_post_interview_analysis
from app.core.database import async_session_factory

async def main():
    interview_id = "8f5a3353-9196-4ba5-93ae-fde414227985"
    print(f"Running analysis for {interview_id}...")
    try:
        await _run_post_interview_analysis(interview_id)
        print("Analysis completed successfully.")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
