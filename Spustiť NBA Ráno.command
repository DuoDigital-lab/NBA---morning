#!/bin/zsh
# Dvojklik v Finderi: aktualizuje dáta z ESPN a spustí appku (aj pre telefón na rovnakej Wi-Fi).
cd "$(dirname "$0")" || exit 1

echo "Aktualizujem dáta z ESPN…"
if python3 -m generator.build > /dev/null 2>&1; then
  echo "Dáta sú aktuálne."
else
  echo "Pozor: aktualizácia mala problém – appka ukáže poslednú platnú verziu."
fi

# Ak appka už beží (napr. z iného okna), len ju otvor.
if lsof -iTCP:8765 -sTCP:LISTEN > /dev/null 2>&1; then
  echo "Appka už beží: http://localhost:8765"
  open -a "Brave Browser" "http://localhost:8765" 2>/dev/null || open "http://localhost:8765"
  exit 0
fi

python3 tools/serve.py 8765 --lan --open
