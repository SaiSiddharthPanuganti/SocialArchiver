import os
import json
import httpx

def list_models():
    # Load saved config
    config_file = "./backend/config.json"
    if not os.path.exists(config_file):
        print("Config file not found. Please save your API Key in the UI first.")
        return
        
    with open(config_file, "r") as f:
        config = json.load(f)
        
    api_key = config.get("gemini_api_key", "")
    if not api_key:
        print("Gemini API key not configured in config.json")
        return
        
    # Query ListModels
    url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print("Available models on your API Key:")
            for m in models:
                name = m.get("name", "")
                supported_methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in supported_methods:
                    print(f" - {name} ({m.get('displayName', '')})")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Failed to query ListModels: {e}")

if __name__ == "__main__":
    list_models()
