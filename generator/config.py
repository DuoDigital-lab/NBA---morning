import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(DOCS_DIR, "data")
STATE_DIR = os.path.join(ROOT, "state")

# Koľko posledných zápasov tímu sa použije na výpočet základnej päťky. 20 ≈ 5–6 týždňov, takže hráč
# s dlhším zranením (napr. 3–4 týždne) z päťky nevypadne; rozhoduje podiel štartov v zápasoch, ktoré odohral.
CORE_WINDOW = 20
# Koľko US dní dozadu sa pri každom behu pregeneruje (neskoré opravy box score).
REBUILD_DAYS = 3
# Koľko US dní dopredu ukazuje kalendár zápasov.
CALENDAR_DAYS = 14
# Typy sezóny z ESPN: 2 = základná časť, 3 = playoff, 5 = play-in.
SEASON_TYPES = {2, 3, 5}

US_TZ = "America/New_York"

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")
