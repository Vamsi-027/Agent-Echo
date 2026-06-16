import json
from anthropic import Anthropic

def select_format(digest_row: dict, pillar: str, media_available: list[str] | None = None) -> str:
    """
    Selects the best post format ('text' | 'image' | 'carousel' | 'video' | 'long_form')
    based on the content pillar, the digest highlights, and any available media files.
    """
    if media_available is None:
        media_available = []
        
    client = Anthropic()
    
    format_schema = {
        "type": "object",
        "properties": {
            "format_type": {
                "type": "string",
                "enum": ["text", "image", "carousel", "video", "long_form", "poll"],
                "description": "The chosen post format"
            },
            "reasoning": {
                "type": "string",
                "description": "Why this format suits the current pillar, highlights, and media details"
            }
        },
        "required": ["format_type", "reasoning"],
        "additionalProperties": False
    }
    
    prompt = (
        "You are an editor choosing the post format for a LinkedIn post.\n"
        "Available Formats:\n"
        "- text: standard text post (concise, high value)\n"
        "- image: post with a single visual asset (diagram, chart, code screenshot)\n"
        "- carousel: swipeable document post (needs multiple slides/images to combine to PDF)\n"
        "- video: short demo/walkthrough video clip\n"
        "- long_form: detailed text essay (typically used when the explanation needs depth)\n"
        "- poll: interactive poll to engage the audience (requires a clear question and 2-4 choice options)\n\n"
        f"Selected Pillar: {pillar}\n"
        f"Available Media files on disk: {json.dumps(media_available)}\n"
        f"Daily Digest:\n"
        f"Highlights:\n{digest_row['highlights_json']}\n"
        f"Categories:\n{digest_row['categories_json']}\n\n"
        "Please select the best format."
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        output_config={"format": {"type": "json_schema", "schema": format_schema}},
        messages=[{"role": "user", "content": prompt}]
    )
    
    result = json.loads(response.content[0].text)
    return result["format_type"]
