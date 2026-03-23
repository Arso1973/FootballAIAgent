"""Application configuration"""
import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
DATA_DIR = BASE_DIR / "data"
HISTORY_FILE = DATA_DIR / "chat_history.json"


def ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_api_keys() -> dict[str, str]:
    """Load API keys from environment."""
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    return {
        "openai": os.getenv("OPENAI_API_KEY", "").strip(),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "tavily": os.getenv("TAVILY_API_KEY", "").strip(),
    }


def get_models_config() -> list[dict]:
    """Load models from config.yaml."""
    if not CONFIG_PATH.exists():
        return _default_models()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("models", _default_models())
    except Exception:
        return _default_models()


def _default_models() -> list[dict]:
    """Default model list if config is missing."""
    return [
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai"},
        {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic"},
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "provider": "anthropic"},
    ]


def get_default_model() -> str:
    """Get default model ID from config."""
    if not CONFIG_PATH.exists():
        return "claude-sonnet-4-6"
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("default_model", "claude-sonnet-4-6")
    except Exception:
        return "claude-sonnet-4-6"
