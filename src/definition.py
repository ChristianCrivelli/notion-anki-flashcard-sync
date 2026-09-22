import requests
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

gemini_key = os.getenv("gemini_key")
if not gemini_key:
    raise RuntimeError("Missing 'gemini_key' in .env")

client = genai.Client(api_key=gemini_key)

def get_definition(word):

    # 1. Free Dictionary API
    try:
        response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        if response.status_code == 200:
            print(f"Source for {word}: Free Dictionary API")
            return response.json()[0]['meanings'][0]['definitions'][0]['definition']
    except Exception as e:
        print(f"Free Dictionary failed: {e}")

    # 2. Merriam-Webster
    try:
        response = requests.get(f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={os.getenv('webster_key')}")
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data[0], dict) and 'shortdef' in data[0]:
                print(f"Source for {word}: Merriam-Webster")
                return data[0]['shortdef'][0]
        else:
            print(f"Merriam-Webster failed: status {response.status_code}")
    except Exception as e:
        print(f"Merriam-Webster failed: {e}")

    # 3. Gemini fallback
    print(f"Falling back to Gemini for '{word}'")
    result = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Give me a single, concise dictionary-style definition for the word: '{word}'. Return only the definition, no extra text."
    )

    return result.text.strip()  