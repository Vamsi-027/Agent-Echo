import sys
import pytest
from unittest.mock import patch, MagicMock
from anthropic_fallback import FallbackAnthropic, apply_patch

@pytest.mark.anyio
@patch("openai.OpenAI")
async def test_anthropic_fallback_to_openai(mock_openai_class):
    # Mock OpenAI client response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_choice = MagicMock()
    mock_choice.message.content = "OpenAI response text"
    
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    
    mock_client.chat.completions.create.return_value = mock_completion

    # Set up FallbackAnthropic
    import os
    os.environ["OPENAI_API_KEY"] = "fake-openai-key"
    fallback = FallbackAnthropic()
    
    # Mock the real client
    fallback.real_client = MagicMock()
    fallback.real_client.messages.create.side_effect = Exception("Your credit balance is too low to access the Anthropic API")

    # Call fallback messages create
    response = fallback.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello fallback"}]
    )

    # Check mock response format matches Anthropic content block schema
    assert response.content[0].text == "OpenAI response text"
    
    # Assert OpenAI chat completion was dispatched
    mock_client.chat.completions.create.assert_called_once()
