#!/bin/sh
# Collecte quotidienne lancée par une tâche planifiée « cron » (hébergement cPanel, sans systemd).
# N'écrit que dans son dossier (code, archive, base) et dans le dossier du site (DESTINATION).
# Exemple de ligne cron (tous les jours à 6 h 30) :
#   30 6 * * * $HOME/barometre/ops/cron.sh >> $HOME/barometre/data/logs/cron.log 2>&1
# Python 3.12 : celui de UV_PYTHON s'il est défini, sinon celui de CloudLinux (/opt/alt) s'il
# existe, sinon celui que uv trouve ou installe.
set -eu
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
if [ -z "${UV_PYTHON:-}" ] && [ -x /opt/alt/python312/bin/python3.12 ]; then
    export UV_PYTHON=/opt/alt/python312/bin/python3.12
fi
cd "$RACINE"
mkdir -p data/logs
echo "===== $(date -Iseconds) cron"
# Dernière version du code publiée sur GitHub (avance rapide seulement ; en cas d'échec, la
# collecte tourne avec le code déjà en place), puis dépendances figées.
git pull --ff-only --quiet || echo "[cron] git pull impossible : code inchangé"
uv sync --frozen --quiet || echo "[cron] uv sync impossible : dépendances inchangées"
# Priorité basse (processeur et disque) : les autres sites du même hébergement passent avant.
PRIO="nice -n 19"
if command -v ionice >/dev/null 2>&1; then PRIO="$PRIO ionice -c 3"; fi
exec $PRIO make --no-print-directory quotidien
