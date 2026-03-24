"""Sync Langfuse secrets from .env to HuggingFace Space."""

from dotenv import load_dotenv
from huggingface_hub import HfApi
import os

load_dotenv()

SPACE_ID = "jim-bo/cli-textual-demo"
SECRETS = [
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_BASE_URL",
]

api = HfApi()

for key in SECRETS:
    value = os.getenv(key)
    if not value:
        print(f"  SKIP {key} (not set)")
        continue
    api.add_space_secret(SPACE_ID, key, value)
    print(f"  SET  {key}")

print("Done.")
