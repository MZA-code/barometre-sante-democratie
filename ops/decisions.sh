#!/bin/sh
# Tâche horaire D7 : relit les décisions prises sur GitHub et republie le site si besoin.
# Pas de `git pull` ici : le code n'est mis à jour que par ops/cron.sh (6 h 30).
# Exemple de ligne cron (toutes les heures, à la 5e minute) :
#   5 * * * * $HOME/barometre/ops/decisions.sh >> $HOME/barometre/data/logs/decisions.log 2>&1
set -eu
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
if [ -z "${UV_PYTHON:-}" ] && [ -x /opt/alt/python312/bin/python3.12 ]; then
    export UV_PYTHON=/opt/alt/python312/bin/python3.12
fi
cd "$RACINE"
mkdir -p data/logs
exec nice -n 19 uv run --frozen python -m ops.decisions
