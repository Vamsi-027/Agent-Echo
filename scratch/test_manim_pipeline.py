import os
import sys
import logging
from pathlib import Path

# Setup logging to console so we can see the full generation progress
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("linkedin-agent.manim_test")

# Ensure project root is in the python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Load environment variables from the project root .env file
from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / ".env")

from generator.media_handler import generate_manim_video

def main():
    # Verify environment variables
    missing_vars = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing_vars.append("ANTHROPIC_API_KEY")
    if not os.environ.get("ELEVENLABS_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        missing_vars.append("ELEVENLABS_API_KEY or OPENAI_API_KEY")
        
    if missing_vars:
        print(f"WARNING: The following environment variables are missing: {', '.join(missing_vars)}")
        print("Please check your .env or export them before running.")
        print("-" * 50)

    # Mock technical digest that will trigger the Manim pipeline
    digest = {
        "highlights_json": '["Reworked the execution engine to run as a finite state machine", "State transitions optimized from O(N) to O(1)", "Implemented fallback handling for error states"]',
        "raw_summary": "Rebuilt the ETL pipeline execution engine using a robust state machine model, optimizing runtimes.",
        "suggested_pillar": "technical_insight"
    }

    output_video = str(project_root / "media" / "test_output_manim.mp4")
    
    print("Starting Manim E2E video generation...")
    print("1. Generating voiceover script via Claude")
    print("2. Synthesizing voiceover audio (with timestamps)")
    print("3. Generating Manim Python scene code matching voiceover timings")
    print("4. Rendering Manim video (with self-repair loop on errors)")
    print("5. Mixing audio and video tracks via ffmpeg")
    print("-" * 50)
    
    success = generate_manim_video(
        date_str="test_run",
        digest=digest,
        output_path=output_video,
    )
    
    if success:
        print("\n" + "=" * 50)
        print(f"SUCCESS! Manim video generated successfully.")
        print(f"Output file: {output_video}")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("FAILED! Manim video generation encountered errors.")
        print("Review the logs above to identify the issue.")
        print("=" * 50)

if __name__ == "__main__":
    main()
