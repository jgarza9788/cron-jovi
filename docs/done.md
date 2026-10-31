# Done

## Before a public release

- [x] 1. Add a license: MIT
- [x] 2. Set up CI, covering Python 3.11 through 3.14
- [ ] 3. Tag a beta release: v0.0.1 *Blaze of Glory*. Tagged locally, before the beta label was added; move the tag, push it, and mark the GitHub release as a pre-release

## Gaps against the design doc

- [x] 5. Add a `window` action to focus, move or close windows
- [x] 6. Make `focus_app` work on niri
- [x] 7. Test on a real niri session: 15 of 15 checks passed in nested niri 26.04, covering the `window` and `workspace` actions, bringing the app forward, and the hotkey config and its command. A physical key press wasn't tested
- [x] 8. Update the design doc: status, GUI toolkit decision, action count, overlap with n8n, Node-RED and Huginn

## Quality

- [x] 9. Add front-end tests for the editor, drag and drop, and undo
- [x] 10. Find and fix the unclosed SQLite connections and file

## New

- [x] 11. Add a Markdown guide for AI agents on creating workflows: `AGENTS.md`
- [x] 12. Search for issues and CVEs and fix them
- [x] 13. Add an About section at the end of Settings: v0.0.1 *Blaze of Glory*
