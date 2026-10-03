---
name: load-commands
description: Resume el estado del repositorio.
hooks:
  PreToolUse:
    - command: echo hola
---

Estado actual: !`git status --short`
