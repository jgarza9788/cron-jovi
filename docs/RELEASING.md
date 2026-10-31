# Making a release

A release is a few steps run from `~/Work/cron-jovi`, always from `main`. `scripts/release/` builds the files and
publishes them. `X.Y.Z` is the version in `cron_jovi/__init__.py`.

```sh
git switch main && git pull
scripts/release/build.sh              # everything except publishing
# ...look at dist-release/vX.Y.Z/, write dist-release/notes.md...
scripts/release/publish.sh            # public: shows everything, asks for a yes
```

## The steps

| Step | What to do | Command | Time |
|---|---|---|---|
| 1 | Set the version, codename and stage. | edit `cron_jovi/__init__.py` | seconds |
| 2 | Run the tests. | `python3 -m unittest discover -s tests`, then `npm ci && npm test` | seconds |
| 3 | Open a PR into `main`, wait for CI, and merge it. Direct pushes to `main` are blocked. | `gh pr create`, then `gh pr merge --admin --merge` | ~2 min |
| 4 | Build the source tarball, the Arch package, the AppImage and `SHA256SUMS` into `dist-release/vX.Y.Z/`. Publishes nothing. | `scripts/release/build.sh` | ~1 min |
| 5 | Test the files in clean containers (below). | `podman run ...` | minutes |
| 6 | Write `dist-release/notes.md` (below). | | minutes |
| 7 | Tag and create the GitHub release with its files. Public. Asks for a yes, and refuses if the release exists unless given `--replace`. | `scripts/release/publish.sh` | seconds |

`build.sh` uses the committed code, and needs `appimagetool` from `~/Work/CaptainFM-tools` (set `TOOLS` to change that).

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

  Install lists each file and the clone lines. Keep the limits from the Reference below.
- **Containers:** install the Arch package in `archlinux:latest` and run a workflow, and do the same with the AppImage
  (`--appimage-extract`, then `squashfs-root/AppRun`, since containers have no FUSE).
- **Publish:** show the notes and the commit first, and get a yes. Never move or delete a tag that is already published
  without the owner saying so. A tag that hasn't been pushed can be moved with `git tag -f -a`.

**Updates:** copies from `install.sh` update themselves from these tags. They install the source of the newest `vX.Y.Z`
release, so a release reaches people as soon as it is published, including pre-releases. Arch and AppImage copies show a
note instead, because they update the way they were installed. Test before you tag, and never reuse a version.

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
- The AppImage always opens in the browser, because its Python can't load the desktop's WebKit.
- The AppImage needs glibc 2.44 or newer, so it starts on rolling distros only (it does not start on Debian 13). It keeps
  its timers and hotkeys only while the file stays in the same place.
- Schedules stop at logout unless `loginctl enable-linger` is on.

**Shipped:** the source tarball, the Arch package (`pacman -U`), the AppImage and `SHA256SUMS`.

**Not shipped:** the AUR, which isn't taking new accounts, so `packaging/aur/` is not published. Also no `.deb`, `.rpm`,
Flatpak or PyPI package.

**Rules:** a release never changes a person's workflows, and shared workflows always arrive switched off.
`install.sh` must keep working without root.
