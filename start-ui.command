#!/bin/zsh
set -e
cd "$(dirname "$0")/ui"
if [[ ! -d node_modules ]]; then
  npm ci
fi
npm run dev &
server_pid=$!
sleep 3
if [[ -d "/Applications/Google Chrome.app" ]]; then
  open -a "Google Chrome" http://localhost:3000
else
  open http://localhost:3000
fi
wait "$server_pid"
