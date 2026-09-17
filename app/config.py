import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


GITHUB_TOKEN = required("GITHUB_TOKEN")
NVIDIA_API_KEY = required("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1",
)
NVIDIA_MODEL = required("NVIDIA_MODEL")
ZULIP_REPO_PATH = Path(required("ZULIP_REPO_PATH"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
MAX_FILE_CHARS = int(os.getenv("MAX_FILE_CHARS", "12000"))