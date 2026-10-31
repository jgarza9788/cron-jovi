# To do

## Before a public release

- [x] 1. Add a license: MIT
- [x] 2. Set up CI, covering Python 3.11 through 3.14
- [ ] 3. Tag a release: v0.0.1 *Blaze of Glory*. Tagged locally; push it once CI passes
- [ ] 4. Add an AUR package. `packaging/aur/` is ready; not test-built or published yet

## Gaps against the design doc

- [x] 5. Add a `window` action to focus, move or close windows
- [x] 6. Make `focus_app` work on niri
- [ ] 7. Test hotkeys and workspace switching on a real niri session. CI checks the config and commands; a live session is still needed
- [x] 8. Update the design doc: status, GUI toolkit decision, action count, overlap with n8n, Node-RED and Huginn

## Quality

- [x] 9. Add front-end tests for the editor, drag and drop, and undo
- [x] 10. Find and fix the unclosed SQLite connections and file

## New

- [x] 11. Add a Markdown guide for AI agents on creating workflows: `AGENTS.md`
- [x] 12. Search for issues and CVEs and fix them
- [x] 13. Add an About section at the end of Settings: v0.0.1 *Blaze of Glory*
