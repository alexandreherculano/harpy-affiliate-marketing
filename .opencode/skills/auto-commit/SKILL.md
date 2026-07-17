---
name: auto-commit
description: After every code edit, stage and commit the changes automatically with a concise commit message
---

## What I do
After EVERY file modification (edit/write tool call):
1. Run `git add <changed_files>`
2. Run `git commit -m "<short message>"`

## When to use me
This skill MUST be used after every single `edit` or `write` operation that modifies source code. Do NOT skip this. Commit immediately after each change, before responding to the user.

## Commit message rules
- Write the title in English, imperative mood (max 72 chars)
- Add a blank line, then a Brazilian Portuguese summary of what was changed:
  ```
  Fix React-Select label detection

  Corrigida a detecção de labels dos componentes React-Select que usam
  elementos irmãos em vez de tags <label>. Agora busca o texto do
  elemento anterior na hierarquia DOM.
  ```

## Post-commit (MANDATORY — execute IMMEDIATELY after commit)
1. **Right after `git commit` succeeds**, send a message to the user with the format:
   ```
   `file_path`: descrição em português brasileiro do problema e solução.
   ```
2. This message is part of the SAME response that runs the commit. Do NOT skip it.
3. Example: `src/cli.py: corrigido seletor do container React-Select que parava no wrapper interno `select__input-container` em vez de subir até o div com id `:r10:`, fazendo com que nenhum dropdown abrisse.`
4. If committing multiple files in a single commit, mention all of them briefly.