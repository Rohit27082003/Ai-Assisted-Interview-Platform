import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent))

try:
    print("Attempting to import get_llm from app.core.llm...")
    from app.core.llm import get_llm
    
    print("Function imported successfully.")
    
    print("Attempting to call get_llm()...")
    llm = get_llm()
    print("get_llm() called successfully.")
    print(f"LLM model: {llm.model}")

except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()

