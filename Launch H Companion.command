#!/bin/zsh
# Finder double-click entry point. The launcher reads private configuration, never secrets from arguments.
cd -- "${0:A:h}"
if [[ -x /usr/bin/python3 ]]; then
  exec /usr/bin/python3 scripts/start-devin-companion.py
fi
exec python3 scripts/start-devin-companion.py
