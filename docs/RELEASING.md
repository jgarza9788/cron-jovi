# Making a release

A release is a short list of steps, run by hand from `~/Work/cron-jovi`. Releases are made from `main` only. There is
nothing to compile and no release files to upload: people install from the git tag with `install.sh`. `X.Y.Z` is the
version in `cron_jovi/__init__.py`.

```sh
cd ~/Work/cron-jovi
git switch main && git pull
# ...work through the steps below...
git push origin vX.Y.Z                                                    # public
gh release create vX.Y.Z --title "Cron Jovi vX.Y.Z Name" --prerelease --notes-file /tmp/cronjovi-notes.md   # public
```

## The steps

| Step | What to do | Command | Time |
|---|---|---|---|
| 1 | Set the version, codename and stage. | edit `cron_jovi/__init__.py` | seconds |
| 2 | Run the Python tests. | `python3 -m unittest discover -s tests` | seconds |
| 3 | Run the front-end tests. | `npm ci && npm test` | seconds |
| 4 | Check the dependencies for known CVEs. | `pip-audit --local` (in a venv with Cron Jovi installed) | seconds |
| 5 | Open a PR into `main`, wait for CI, and merge it. Direct pushes to `main` are blocked. | `gh pr create`, then `gh pr merge --admin --merge` | ~2 min |
| 6 | Write the release notes (below). | `/tmp/cronjovi-notes.md` | minutes |
| 7 | Tag that commit. | `git tag -a vX.Y.Z -m "vX.Y.Z Name"` | seconds |
| 8 | Push the tag and create the GitHub release. Public. | the two commands above | seconds |

## Where things are set

| Value | Where | Now |
|---|---|---|
| Version | `__version__` in `cron_jovi/__init__.py`, the only place it is set (scheme `0.0.N`) | `0.0.1` |
| Codename | `__codename__` in `cron_jovi/__init__.py`, chosen by hand each release | v0.0.1 *Blaze of Glory* |
| Stage | `__stage__` in `cron_jovi/__init__.py` | `Beta` |

Settings → About, `cronjovi --version` and the package metadata all read these. The classifier in `pyproject.toml` is
the exception: change it by hand when the stage changes, and remove the beta notice from the top of the README.

## Before you start
Everything is committed on `main` and CI passes. CI runs the Python tests on 3.11 to 3.14, the front-end tests, the
dependency audit, and the niri checks against the real `niri` program.

## What stays by hand
- **Desktop check:** close the app, run `./install.sh`, then open Cron Jovi and try a workflow on your own desktop. Tests
  use fake tools, so this is the only check of real windows, hotkeys and timers on your desktop. Never run `install.sh` with the app open.
- **Notes:** write them in plain words with these headings:

  ```markdown
  # Cron Jovi vX.Y.Z Name

  ## What is new
  ## Install
  ## Limits
  ```

  Install is the clone, `git checkout vX.Y.Z` and `./install.sh` lines. Keep the limits from the Reference below.
- **Publish:** show the notes and the commit first, and get a yes. Never move or delete a tag that is already published
  without the owner saying so. A tag that hasn't been pushed can be moved with `git tag -f -a`.

**Updates:** Cron Jovi updates itself from these tags. It installs the source of the newest `vX.Y.Z` release, so a release
reaches people as soon as it is published, including pre-releases. Test before you tag, and never reuse a version.

**Who can do what:** only the owner can merge into `main`, or create, move or delete `v*` tags. Both are GitHub rulesets:
"Protect main" and "Protect release tags". Keep the repo free of collaborators with write access, since write access
is what allows creating a release.

## After
Move what shipped into `docs/done.md`, and check the new release shows on the GitHub page with the right tag. While the
stage is `Beta`, keep `--prerelease` on the release.

---

## Reference

**What is supported:** Linux with systemd and Python 3.11 or newer, on Wayland with Hyprland or niri. Theme support is for
Omarchy. Without a compositor it still works, apart from hotkeys, `workspace` and `window`.

**Limits (put them in the notes):**
- Beta. Expect rough edges.
- On niri, hotkeys have been checked up to the key press itself, not with a physical keyboard.
- The app window needs `webkit2gtk-4.1` and `python-gobject`. Without them it opens in the browser.
- Schedules stop at logout unless `loginctl enable-linger` is on.

**Not shipped:** the AUR, which isn't taking new accounts, so `packaging/aur/` is not published. Also no `.deb`, `.rpm`,
Flatpak or PyPI package.

**Rules:** a release never changes a person's workflows, and shared workflows always arrive switched off.
`install.sh` must keep working without root.
