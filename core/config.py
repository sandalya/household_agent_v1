"""Конфігурація Household Agent."""
import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY")
OWNER_CHAT_ID    = int(os.getenv("OWNER_CHAT_ID", "0"))
ADMIN_IDS        = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

DATA_DIR   = BASE_DIR / "data"
LOGS_DIR   = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"

CLAUDE_MODEL      = "claude-sonnet-4-5"
CLAUDE_MAX_TOKENS = 1024
