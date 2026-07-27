# Best Practice: Symlink for Skills with Their Own Git Repo

## Problem
When a skill has its own substantial Git repository (e.g. `portfolio-analysis`), keeping a full copy inside `~/.hermes/skills/` leads to:
- Duplicated files
- Risk of drift between the Hermes copy and the real repo
- Conflicting `SKILL.md` files

## Recommended Pattern

1. Keep the canonical code and `SKILL.md` in the real repository (e.g. `~/portfolio-analysis`).
2. Create a symlink in the Hermes skills directory:
   ```bash
   ~/.hermes/skills/<category>/<skill-name> -> ~/portfolio-analysis
   ```
3. Move any Hermes-specific reference files (architecture decisions, delivery preferences, etc.) into a `references/` folder inside the real repo.
4. Update `SKILL.md` to document the symlink pattern and point to the real repository.

## Benefits
- Single source of truth
- Cleaner Hermes skill directory
- Easier maintenance and backups
- Self-describing skill via `repository` field in SKILL.md

## Example
```bash
ln -s ~/portfolio-analysis ~/.hermes/skills/openclaw-imports/portfolio-analysis
```

This pattern should be used for any skill that has grown beyond a simple helper into its own maintained codebase.
