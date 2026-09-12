import json
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
# --- Credentials ---
# Line 9 is now completely safe:
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIST_ID = os.getenv("GIST_ID")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

app = FastAPI()

# Allow your frontend to talk to this local API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class WatchdogConfig(BaseModel):
    timeout_minutes: int
    enabled: bool

@app.get("/api/config")
def get_config():
    """Fetches the current live config from GitHub."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    response = requests.get(url, headers=HEADERS)
    content = response.json()["files"]["config.json"]["content"]
    return json.loads(content)

@app.post("/api/config")
def update_config(config: WatchdogConfig):
    """Pushes new settings from your frontend to the Gist."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = {
        "files": {
            "config.json": {
                "content": config.model_dump_json()
            }
        }
    }
    requests.patch(url, headers=HEADERS, json=payload)
    return {"status": "success", "new_config": config.model_dump()}