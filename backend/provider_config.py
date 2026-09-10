"""Backend-only provider configuration. Never serialize this module to clients."""
import os
from pathlib import Path
from dotenv import load_dotenv

# An explicit path prevents searching parents. Shell values win (including test blanks).
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def api_key(name):
    return os.getenv(name, "").strip()


SARVAM_MODEL = "saaras:v3"
NVIDIA_MODEL = "google/gemma-4-31b-it"
STT_TIMEOUT = 45
NLP_TIMEOUT = 70
