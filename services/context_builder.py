from typing import List

def build_final_prompt(user_query: str, summaries: List[dict]) -> str:
    context_blocks = "\n\n".join([
        f"[{item['title']}]\n{item['summary']} (Sentiment: {item['sentiment']})" for item in summaries
    ])
    return f"""You are a real-time financial assistant. Use the latest news context to answer:

🔍 User Query: {user_query}

🗞️ Market Context:
{context_blocks}

📊 Provide an insightful, market-aware answer.
"""
