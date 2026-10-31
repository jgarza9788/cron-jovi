# To do

Finished work is in `docs/done.md`. The steps for a release are in `docs/RELEASING.md`.

## Release

- [ ] 1. Commit the beta label, `docs/done.md`, `docs/RELEASING.md` and this file. Keep `logs_111672315389/` out of git
- [ ] 2. Close the app, run `./install.sh`, and try a workflow, the `window` action and Settings → About. The installed copy is still 0.1.0, without the security fixes
- [ ] 3. Move the local `v0.0.1` tag to the commit with the beta label, once CI passes on it
- [ ] 4. Push the tag and create the GitHub pre-release: v0.0.1 *Blaze of Glory*

## From the CI logs

- [ ] 5. Update the GitHub Actions in `.github/workflows/ci.yml`. `actions/checkout@v4`, `actions/setup-python@v5` and `actions/setup-node@v4` run on the deprecated Node.js 20; the latest are v7 for all three
- [ ] 6. Update jsdom from 26 to 30. npm warns that `whatwg-encoding`, which it pulls in, is deprecated
- [ ] 7. Check CI still passes on Ubuntu 26. `ubuntu-latest` moves to it from October 19, 2026
