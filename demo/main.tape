# demo/main.tape — agent-session-manager (asm): combined Claude+Codex dashboard
# Run: cd <repo> && vhs demo/main.tape
# Sandboxed HOME (/tmp/asm-demo) so no real project data is shown.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 13
Set Width 1300
Set Height 760
Set Theme "Dracula"
Set TypingSpeed 38ms
Set Framerate 24
Set LoopOffset 5%

Env PS1 "$ "

# 1. Launch — combined Claude + Codex dashboard (rows tagged C / X)
Type "HOME=/tmp/asm-demo asm --no-update-check"
Enter
Sleep 5500ms

# 2. Cycle the usage period (Daily -> Weekly -> Monthly -> Daily)
Tab
Sleep 1600ms
Tab
Sleep 1600ms
Tab
Sleep 1400ms
Type "q"
Sleep 1800ms

# 3. Same dashboard, filtered to Claude
Type "HOME=/tmp/asm-demo asm --source claude --no-update-check"
Enter
Sleep 4500ms
Type "q"
Sleep 1600ms

# 4. ...and filtered to Codex
Type "HOME=/tmp/asm-demo asm --source codex --no-update-check"
Enter
Sleep 4500ms
Type "q"
Sleep 1500ms
