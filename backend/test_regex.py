import re

def clean_json_output(text: str) -> str:
    """Clean LLM output to extract JSON."""
    text = text.strip()
    # Remove markdown code blocks
    match = re.search(r"```(?:json)?\s*(.*)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return text.strip()

test_input = """```json
{
    "skills_score": 90,
    "projects_score": 80
}
```"""

cleaned = clean_json_output(test_input)
print(f"Input length: {len(test_input)}")
print(f"Output: '{cleaned}'")

import json
try:
    parsed = json.loads(cleaned)
    print("JSON Parse Success!")
    print(parsed)
except Exception as e:
    print(f"JSON Parse Failed: {e}")
