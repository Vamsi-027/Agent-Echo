import json
import logging
from anthropic import Anthropic

logger = logging.getLogger("linkedin-agent.generator.conceptual_image_selector")

IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "A very short, punchy technical slide title (under 40 chars) summarizing the post topic."
        },
        "points": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "string",
                "description": "Key technical point or metric (under 70 chars). Avoid generic corporate fluff."
            },
            "description": "Exactly 3 distinct highlights or lessons learned."
        }
    },
    "required": ["title", "points"],
    "additionalProperties": False
}

def extract_image_details(text: str, topic: str) -> dict:
    """
    Use Claude to extract a slide title and 3 key points from a post's draft content.
    """
    client = Anthropic()
    system_prompt = (
        "You are a presentation designer converting a technical LinkedIn post into a premium slide graphic.\n"
        "Extract a single key title (max 40 chars) and exactly 3 core technical points (max 70 chars each) "
        "that summarize the post. Do not introduce generic placeholders."
    )
    user_prompt = f"Topic: {topic}\n\nPost Content:\n{text}"
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            output_config={"format": {"type": "json_schema", "schema": IMAGE_SCHEMA}},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return json.loads(response.content[0].text)
    except Exception as e:
        logger.error(f"Failed to extract image details with Claude: {e}")
        return {
            "title": topic[:35],
            "points": [
                "Key lesson or architectural takeaway",
                "Core performance metrics or system details",
                "Next steps or resolution principles"
            ]
        }
