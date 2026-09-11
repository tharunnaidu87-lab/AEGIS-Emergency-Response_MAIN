"""Backend-only provider configuration.

Secrets are loaded only on the backend.
Never expose this module or provider keys to the frontend.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent

# Load only backend/.env.
# Existing shell/environment values take priority.
load_dotenv(BACKEND_DIR / ".env", override=False)


def api_key(name: str) -> str:
    return os.getenv(name, "").strip()


# Saaras v4 is used for the improved multilingual demo path.
SARVAM_MODEL = os.getenv(
    "SARVAM_STT_MODEL",
    "saaras:v4",
).strip()

# Smaller/faster NVIDIA hosted model for emergency extraction.
NVIDIA_MODEL = os.getenv(
    "NVIDIA_NLP_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
).strip()


# Provider request limits.
STT_TIMEOUT = 60
NLP_TIMEOUT = 60