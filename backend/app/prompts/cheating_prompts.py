from langchain_core.prompts import ChatPromptTemplate

CHEATING_CHECK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an interview integrity checker. Analyze if the answer shows signs of:
1. Reading from a pre-prepared script (unnaturally perfect, textbook-like)
2. Being dictated by someone else (inconsistent expertise level)
3. Being copy-pasted from a source (overly formal, includes references)

Question: {question}
Answer: {answer}"""),
    ("human", "Analyze this Q&A pair."),
])
