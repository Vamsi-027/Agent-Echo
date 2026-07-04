import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")
if not api_key:
    print("Error: ELEVENLABS_API_KEY not found in .env")
    exit(1)

url = "https://api.elevenlabs.io/v1/voices"
headers = {
    "xi-api-key": api_key
}

response = requests.get(url, headers=headers)
if response.status_code != 200:
    print(f"Error fetching voices: {response.status_code} - {response.text}")
    exit(1)

voices = response.json().get("voices", [])
print(f"Found {len(voices)} available voices:")
print("-" * 80)
for v in voices:
    labels = v.get("labels", {})
    gender = labels.get("gender", "unknown")
    accent = labels.get("accent", "unknown")
    description = labels.get("description", "unknown")
    use_case = labels.get("use_case", "unknown")
    
    # Filter for female voices or print all
    print(f"Name: {v['name']}")
    print(f"Voice ID: {v['voice_id']}")
    print(f"Labels: Gender={gender}, Accent={accent}, UseCase={use_case}")
    print(f"Description: {v.get('description') or description}")
    print("-" * 80)
