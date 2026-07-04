import asyncio
import os
import sys
import re
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def fallback_intent_parse(text: str) -> dict | None:
    text_lower = text.lower().strip()
    
    # 1. Action commands with IDs (e.g. "approve draft 71")
    approve_match = re.search(r"\b(?:approve|post|queue|publish)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if approve_match:
        return {"intent": "approve", "draft_id": int(approve_match.group(1))}

    skip_match = re.search(r"\b(?:skip|reject|delete|discard)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if skip_match:
        return {"intent": "skip", "draft_id": int(skip_match.group(1))}

    edit_match = re.search(r"\b(?:edit|change|modify)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if edit_match:
        instruction = ""
        instruction_match = re.search(r"\b(?:edit|change|modify)\s*(?:draft)?\s*\d+\s*(?:to|and)?\s*(.+)", text, re.IGNORECASE)
        if instruction_match:
            instruction = instruction_match.group(1).strip()
        return {"intent": "edit", "draft_id": int(edit_match.group(1)), "edit_instruction": instruction}

    # 2. Simple action commands without IDs
    if text_lower in ("approve", "yes", "confirm"):
        return {"intent": "approve"}
    if text_lower in ("skip", "reject", "no"):
        return {"intent": "skip"}
    if text_lower.startswith("edit ") or text_lower.startswith("change ") or text_lower.startswith("make it "):
        return {"intent": "edit", "edit_instruction": text}
        
    # 3. Specific drafts on topic / visual
    topic_patterns = [
        r"(?:write|post|draft|make a post|create a post|create a draft)\s+(?:about|on|with video of|with a video of|with a visual of|with visual of)\s+(.+)",
        r"topic:\s*(.+)"
    ]
    for pattern in topic_patterns:
        match = re.search(pattern, text_lower)
        if match:
            orig_match = re.search(pattern, text, re.IGNORECASE)
            if orig_match:
                topic = orig_match.group(1).strip()
                return {"intent": "draft_from_topic", "topic": topic}
            
    # 4. Draft from activity
    if any(k in text_lower for k in ("make a post", "generate post", "create post", "draft post", "generate draft", "make draft")):
        return {"intent": "draft_from_activity"}
        
    # 5. Queue/scheduled status
    if any(k in text_lower for k in ("queue", "scheduled", "show queue", "next post")):
        return {"intent": "queue_status"}
        
    # 6. Analytics
    if any(k in text_lower for k in ("analytics", "metrics", "performance", "how are posts doing")):
        return {"intent": "analytics_summary"}
        
    # 7. Trigger pipeline
    if any(k in text_lower for k in ("run pipeline", "trigger pipeline", "run the pipeline")):
        return {"intent": "trigger_pipeline"}

    return None

async def main():
    test_cases = [
        "make a post with video of echo v2 launch",
        "approve draft 71",
        "reject draft 69",
        "edit draft 71 to make it shorter",
        "make it punchier",
        "what's scheduled in queue?",
        "how are my posts doing?",
        "run pipeline",
        "make a post about new features",
    ]
    for text in test_cases:
        parsed = fallback_intent_parse(text)
        print(f"Text: '{text}' -> {parsed}")

if __name__ == "__main__":
    asyncio.run(main())
