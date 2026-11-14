"""Настройки бота: какие лаборатории считаем топовыми и где лежат данные."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEADERBOARD_PATH = DATA_DIR / "leaderboard.json"
RECENT_PATH = DATA_DIR / "recent.json"
UNMATCHED_PATH = DATA_DIR / "unmatched.json"
STATE_PATH = ROOT / "state.json"
ALIASES_PATH = ROOT / "aliases.json"

# Префикс id в OpenRouter -> человеческое имя лаборатории.
# Хочешь больше или меньше лабораторий — правь только этот словарь.
LABS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google DeepMind",
    "x-ai": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "meta-llama": "Meta",
    "meta": "Meta",
    "mistralai": "Mistral",
    "moonshotai": "Moonshot",
    "z-ai": "Z.ai",
    "minimax": "MiniMax",
    "baidu": "Baidu",
    "bytedance": "ByteDance",
    "alibaba": "Alibaba",
}

# Организация в рейтинге LMArena -> префиксы id в OpenRouter.
ARENA_ORGS = {
    "openai": ["openai"],
    "anthropic": ["anthropic"],
    "google": ["google"],
    "meta": ["meta-llama"],
    "xai": ["x-ai"],
    "x-ai": ["x-ai"],
    "deepseek": ["deepseek"],
    "qwen": ["qwen", "alibaba"],
    "alibaba": ["qwen", "alibaba"],
    "moonshot": ["moonshotai"],
    "moonshotai": ["moonshotai"],
    "mistral": ["mistralai"],
    "zhipu": ["z-ai"],
    "z-ai": ["z-ai"],
    "minimax": ["minimax"],
    "baidu": ["baidu"],
    "bytedance": ["bytedance"],
    "nvidia": ["nvidia"],
    "cohere": ["cohere"],
}

# Красивые имена организаций для постов и рейтинга.
ORG_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "meta": "Meta",
    "xai": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "alibaba": "Alibaba",
    "moonshot": "Moonshot",
    "mistral": "Mistral",
    "zhipu": "Z.ai",
    "minimax": "MiniMax",
    "baidu": "Baidu",
    "bytedance": "ByteDance",
    "nvidia": "NVIDIA",
    "cohere": "Cohere",
    "microsoft": "Microsoft",
    "amazon": "Amazon",
    "nous": "Nous Research",
}

# Сколько постов максимум за один запуск. Остальное уйдёт дайджестом.
MAX_POSTS_PER_RUN = 3

# Насколько старую по дате создания модель ещё считаем «новой».
NEW_WINDOW_DAYS = 7

# Сколько дней храним записи для команды /new.
RECENT_DAYS = 30
