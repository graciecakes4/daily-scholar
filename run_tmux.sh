#!/bin/bash

SESSION="dsscholar"

# If session already exists, just attach and exit
tmux has-session -t $SESSION 2>/dev/null
if [ $? -eq 0 ]; then
  echo "Attaching to existing session: $SESSION"
  tmux attach -t $SESSION
  open http://localhost:3000
  exit 0
fi

# Create new detached session
tmux new-session -d -s $SESSION

# Pane 1: Frontend
tmux send-keys -t $SESSION "cd ~/daily-scholar/frontend && npm run dev" C-m

# Split vertically (left/right)
tmux split-window -h -t $SESSION

# Pane 2: Backend
tmux send-keys -t $SESSION "cd ~/daily-scholar && source venv/bin/activate && uvicorn backend.main:app --reload" C-m

# Attach to session
tmux attach -t $SESSION

# Open browser (runs after you attach)
open http://localhost:3000
