# GTNH Prism Installer

**English** | [Türkçe](README.tr.md)

A Windows/Linux program (GUI + CLI) that lists GregTech: New Horizons (GTNH) releases, installs them into
**Prism Launcher**, and performs the file transfer described in the official "Updating → Method 1" guide.

## Features
- Fetches the GTNH version list from the official `versions.json` manifest; pick a version and install it as a
  Prism instance.
- Language prompt on startup (English / Türkçe). If the system language is Turkish, Turkish is preselected;
  otherwise English.
- Dark theme.
- Java defaults to **Java 25** (or the newest version the pack supports). If it is not installed, it is downloaded
  automatically from Adoptium and installed into Prism's `java` folder.
- Tick the "Java setup" box to choose Java yourself: **Detect** (finds Java installations on your computer; click
  one to select its path), **Browse**, or **Download Java** as in Prism (Mojang / Adoptium / Azul Zulu /
  IBM Semeru, major version, version table, "Recommended" filter). Settings are written to the instance's
  `instance.cfg`.
- **Upgrade:** copies the files listed in the guide from an old instance to the new one (the old instance is never
  deleted or modified). Optional steps are checkboxes: GregTech Pollution, main menu music, Space Elevator
  animation, lwjgl3ify fullscreen, Tesla Tower animation, Tinkers classic crafting table, InGameInfoXML,
  ServerUtilities, extra mods, memory and JVM arguments.
- Warns about large version jumps (e.g. 2.6 → 2.8); the CLI requires `--force` to proceed.
- Interface available in Turkish/English (`--lang tr|en`, or `GTNH_LANG`).

## Usage
GUI: `gtnh-prism-installer` (no arguments). CLI: `gtnh-prism-installer-cli`

```
gtnh-prism-installer-cli list [--all]
gtnh-prism-installer-cli instances
gtnh-prism-installer-cli java-list adoptium 21
gtnh-prism-installer-cli install 2.9.2 --java adoptium:25
gtnh-prism-installer-cli update 2.9.2 --from "GT New Horizons 2.8.4" --java adoptium:25 --optional pollution,menu_music
```
`--optional` values: `ingameinfo, pollution, menu_music, space_elevator, lwjgl3ify, tesla_tower, tinkers_layout, serverutilities` (or `all`).

After upgrading, if the game asks about "missing blocks/items" the first time you open your world, choose **Yes**
(on a server, run `/fml confirm`). Back up your worlds regardless.

## Development
```
pip install -r requirements-dev.txt
python -m pytest -q
python run_gtnh_installer.py
pyinstaller --onefile --windowed --name gtnh-prism-installer run_gtnh_installer.py
```
GitHub Actions (`.github/workflows/build.yml`) runs the tests and builds Windows and Linux executables;
on a `v*` tag it attaches them to the release.

## Notes
Adoptium and Semeru installs were tested live. The GTNH download server, Azul and Mojang endpoints were not
reachable from the development environment, so they were tested with a mock server/fixtures.
