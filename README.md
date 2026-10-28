# Armored Core Launcher

Fan-made launcher for every mainline Armored Core before Armored Core VI (PS1, PS2, PSP, PS3).
It downloads and manages the official emulators (DuckStation, PCSX2, PPSSPP, RPCS3) for you,
shows cover art and lore, and launches games with one click.

## Download (for players)
Go to the Releases page. "Latest build (main)" is rebuilt automatically on every commit; versioned releases (v1.0, ...) are stable. Download ArmoredCoreLauncher.exe from either. No Python needed. Windows may show a SmartScreen "unknown publisher" warning because the app is unsigned: choose More info > Run anyway.

## Build the .exe (Windows)
Option A - local: install Python 3.13 or 3.12 from python.org (avoid brand-new versions like 3.15) (tick "Add to PATH"), then double-click `build.bat`.
Output: `dist\ArmoredCoreLauncher.exe`.

Option B - no Python on your machine: create a GitHub repo, upload these files (keep `.github/workflows`),
open the Actions tab > "Build Windows app" > Run workflow, then download the artifact.
Push a tag like `v1.0` to publish it as a Release people can download.

## Use
1. Run the exe. Click INSTALL EMULATORS (first time only).
2. IMPORT BIOS: supply your own PS1/PS2 BIOS and PS3 firmware.
3. ADD FOLDER: point at your own game dumps and choose the platform.
4. Pick a game, press SORTIE. The ARCHIVE tab has lore and history for every game.

## Legal
No games, BIOS, firmware or keys are included or downloaded. You must own and dump your own copies.
Cover art and screenshots (libretro-thumbnails) and text (Wikipedia) are fetched at runtime into a local cache and are not bundled;
Armored Core and its artwork belong to FromSoftware / Bandai Namco. Unofficial fan project.

## Features
- Startup PRE-SORTIE SYSTEM CHECK: installs emulators and asks for your BIOS/firmware files.
- Checks for emulator updates at startup and auto-updates them (toggle in System Check). Saves are kept.
- WHITE GLINT and NEXT themes (SWITCH THEME), favorites, search (Ctrl+F), Enter to launch.
- ARCHIVE tab with lore, box art and screenshots; BACKUP SAVES zips emulator save folders.
- GAME SETTINGS (per game): resolution scale, frame limit, widescreen and RPCS3 Write Color Buffers, written into the emulator's own config on every SORTIE. Presets come from the RPCS3 and PCSX2 wikis where documented.
- PS3 automation: GET GAME UPDATE fetches the latest official title update from Sony's update server (checksum-verified) and installs it via RPCS3; firmware can be fetched from the link on RPCS3's quickstart page.
- SAVE SLOTS (5 per console), CONTROLLER SETUP shortcut, VSync/anisotropic settings for PS3.
- RESET / UNINSTALL: tick what to remove (settings, cache, downloads, save slots, emulators) or do a FULL UNINSTALL. Game files are never touched.
- Emulators are launched with a clean environment (fixes RPCS3's "vcruntime140.dll incorrectly installed" error when running from the packaged exe).
- CONTROLLERS window: live Xbox/XInput pad check and one-click access to each emulator's controller settings.
- If an emulator reports a DLL error when started from the packaged exe, turn on "Compatibility launch" in System Check.
- DIAGNOSE LAST RUN (PS3 game settings): reads RPCS3's log, lists errors, suggests likely causes and copies a report. Offered automatically if a PS3 game closes within ~2.5 minutes.
- Armored Core VI: Fires of Rubicon launches through Steam (auto-detected; LOCATE STEAM FOLDER in System Check). Lore, box art and screenshots included.
- SOUNDTRACKS tab: composers, eras and the tracks fans name most often, with a YouTube search button.
- Resolution defaults to AUTO (matches your display). Game settings are applied only while a game runs; your own emulator settings are restored when it closes.
- ACHIEVEMENTS tab (RetroAchievements): shows your profile, progress and leaderboards for Armored Core sets on PS1/PS2/PSP. Needs your own RetroAchievements username and Web API key (kept only in the launcher's settings file). To earn achievements, enable RetroAchievements inside DuckStation, PCSX2 or PPSSPP.
- MUSIC tab: built-in player (mp3, wav, wma, midi; flac/m4a/ogg depend on Windows codecs) with playlist, loop, shuffle, seek and volume. Pauses while a game runs.

## Support
If this launcher is useful, you can support its development on Ko-fi: https://ko-fi.com/crimzarkin

## More features
- 8 themes (WHITE GLINT, NEXT, RUBICON, CORAL, ARQUEBUS, BALAM, TERMINAL, NIGHTFALL): SYSTEM CHECK > THEMES.
- Library: sort (release / recent / most played / name), right-click menu, ADD GAME MANUALLY for oddly named files, hide games, desktop shortcuts that launch a game directly (`ArmoredCoreLauncher.exe --play "Armored Core 3"`), library and playtime totals, and a "new build available" notice.
- Safety: automatic save backup after each sortie (newest 10 kept per console), a BIOS/firmware check before launch, COPY SUPPORT INFO for bug reports.
- Controller navigation: move the highlight with the D-pad or left stick, A select, B back, LB/RB switch tabs, BACK opens System Check. In the Library: LT/RT change platform, X settings, Y favorite, START sortie. In Music: LT/RT previous/next, X stop, Y shuffle, START play/pause. Works with Xbox pads (XInput); PlayStation pads work through Steam Input or DS4Windows. Toggle it in CONTROLLERS.
