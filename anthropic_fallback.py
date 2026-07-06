import sys
import logging
import json

logger = logging.getLogger("linkedin-agent.anthropic_fallback")

# Backup the original anthropic module
try:
    import anthropic
    OriginalAnthropic = anthropic.Anthropic
except ImportError:
    OriginalAnthropic = None

class FallbackAnthropic:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        if OriginalAnthropic:
            try:
                self.real_client = OriginalAnthropic(*args, **kwargs)
            except Exception:
                self.real_client = None
        else:
            self.real_client = None
            
        self.messages = FallbackMessages(self.real_client)

class FallbackMessages:
    def __init__(self, real_client):
        self.real_client = real_client

    def create(self, **kwargs):
        # 1. Try real Anthropic first
        original_error = None
        if self.real_client:
            try:
                return self.real_client.messages.create(**kwargs)
            except Exception as e:
                original_error = e
                err_str = str(e)
                # Only fall back to OpenAI for billing/credit issues
                if "credit balance" in err_str.lower() or "billing" in err_str.lower() or "budget" in err_str.lower():
                    logger.warning(f"Anthropic billing issue ({err_str}). Falling back to OpenAI...")
                else:
                    # Re-raise so the caller sees the real error
                    raise
        else:
            logger.info("No real Anthropic client available. Falling back to OpenAI...")

        # 2. OpenAI Fallback
        import openai
        import os
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            if original_error:
                raise RuntimeError(f"OPENAI_API_KEY not set; original Anthropic error: {original_error}") from original_error
            raise RuntimeError("OPENAI_API_KEY is not set in .env. Cannot perform OpenAI fallback.")
            
        openai_client = openai.OpenAI(api_key=api_key)
        
        # Map parameters
        system_prompt = kwargs.get("system", "")
        anthropic_messages = kwargs.get("messages", [])
        
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
            
        for msg in anthropic_messages:
            openai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
            
        # Select fallback model
        model = "gpt-4o"
        
        # Configure output format using OpenAI's strict JSON schema translation
        response_format = None
        output_config = kwargs.get("output_config")
        if isinstance(output_config, dict):
            fmt = output_config.get("format", {})
            if fmt.get("type") == "json_schema" and "schema" in fmt:
                schema_dict = fmt["schema"]
                
                def make_strict(sub_schema):
                    if not isinstance(sub_schema, dict):
                        return sub_schema
                    if sub_schema.get("type") == "object":
                        sub_schema["additionalProperties"] = False
                        if "properties" in sub_schema:
                            props = sub_schema["properties"]
                            sub_schema["required"] = list(props.keys())
                            for k, v in props.items():
                                props[k] = make_strict(v)
                    elif sub_schema.get("type") == "array" and "items" in sub_schema:
                        sub_schema["items"] = make_strict(sub_schema["items"])
                    return sub_schema
                
                import copy
                openai_schema = make_strict(copy.deepcopy(schema_dict))
                
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "schema": openai_schema,
                        "strict": True
                    }
                }
        
        logger.info(f"Dispatching fallback chat completion to OpenAI model={model}")
        res = openai_client.chat.completions.create(
            model=model,
            messages=openai_messages,
            max_tokens=kwargs.get("max_tokens", 1000),
            temperature=kwargs.get("temperature", 0.7),
            response_format=response_format
        )
        
        output_text = res.choices[0].message.content
        
        # Ensure returned object behaves like Anthropic's response object:
        # response.content[0].text
        class MockContentBlock:
            def __init__(self, text):
                self.text = text
                
        class MockResponse:
            def __init__(self, text):
                self.content = [MockContentBlock(text)]
                
        return MockResponse(output_text)

# Patch the sys.modules to return our Fallback class when importing anthropic
class PatchedAnthropicModule:
    Anthropic = FallbackAnthropic
    # Export other items from real module if they exist
    def __getattr__(self, name):
        if "anthropic_backup" in sys.modules and hasattr(sys.modules["anthropic_backup"], name):
            return getattr(sys.modules["anthropic_backup"], name)
        raise AttributeError(f"module 'anthropic' has no attribute '{name}'")

def apply_patch():
    # If not already patched, back up real anthropic module and swap
    if "anthropic_backup" not in sys.modules:
        if "anthropic" in sys.modules:
            sys.modules["anthropic_backup"] = sys.modules["anthropic"]
        sys.modules["anthropic"] = PatchedAnthropicModule()
        logger.info("Successfully applied Anthropic -> OpenAI fallback monkeypatch.")
