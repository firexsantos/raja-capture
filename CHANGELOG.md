# Changelog

All notable changes to Raja Capture are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.4.1] - 2026-11-17

### Fixed
- Scrolling capture kept capturing without scrolling and could not be closed: a setting saved by
  older versions silently switched it to manual mode with the control panel hidden.
  Auto-scroll is now the default again and the choice is only remembered when it was visible.
- Manual scrolling capture keeps its panel (with *Selesai*) visible instead of hiding it.
- Scrolling capture can no longer run forever: it stops when the page does not move, when
  frames cannot be stitched, and after at most 4 minutes / 200 frames, with a clear message.
- Wayland auto-scroll now explains that GNOME's *Allow Remote Interaction* switch must be turned
  on, and shows a clear message (instead of failing silently) when it was left off.

### Changed
- Clicking the tray icon or opening Raja Capture from the app menu stops a running
  scrolling capture.

## [0.4.0] - 2026-11-17

### Added
- Auto-scroll for scrolling capture on Wayland through the RemoteDesktop portal (GNOME asks
  once and remembers the choice); the pointer is moved onto the selected area automatically.
- Scrolling capture can be stopped from the tray (*Hentikan tangkap scroll*) or by pressing
  the scrolling-capture hotkey again.

### Fixed
- Scrolling capture on Wayland produced broken results: the control panel and the toolbar
  appeared inside the captured frames. Both are now hidden while capturing.
- Frames were grabbed on a fixed timer, sometimes in the middle of a smooth-scroll animation;
  capture now scrolls, waits for the content to settle, then grabs.
- Capture stops automatically at the end of the page (or a few seconds after manual scrolling
  stops), detects an inverted wheel direction and takes smaller steps when it scrolls too far.

## [0.3.0] - 2026-11-17

### Added
- In-app update notifications: Raja Capture checks GitHub Releases at startup and every
  6 hours, and shows a popup with the new version and its release notes.
- One-click upgrade: the Windows installer, AppImage and `.deb` builds download, verify
  (SHA-256) and install the new version, then restart automatically.
- *Check for updates* and *About* entries in the tray menu; update options in Settings → System.
- `CHANGELOG.md`, with the latest entries mirrored into the README and used as release notes.

### Fixed
- Wayland/GNOME: capturing failed with "Portal Screenshot gagal (kode 2)" when Raja Capture
  was installed from the `.deb`/app menu. GNOME requires a one-time screenshot permission that
  it only asks for while the app has focus; Raja Capture now requests it from a focused dialog
  (with a *reset* option if it was denied before) and retries the capture.

## [0.2.0] - 2026-11-17

### Added
- Resize handles for rectangles, ellipses, highlights, pixelate areas, lines and arrows.
- Audio recording: microphone, system audio, or both.
- *Send* menu: upload to Imgur or a custom server, upload history, email attachment,
  open with another program, copy as file, reveal in folder.
- Installers: AppImage, `.deb`, Windows setup and portable zip, built by GitHub Actions.
- MIT license, project website and a new README.

### Fixed
- Magnifier was dimmed while dragging a selection.
- Settings tab label "Rekam & OCR" displayed incorrectly.

## [0.1.0] - 2026-11-17

### Added
- First release: full screen, window, region and scrolling capture with delay timer.
- Annotation editor with arrows, shapes, text, highlighter, step numbers and pixelate;
  crop, resize, rotate, flip, undo/redo; save as PNG/JPG/BMP/WEBP/PDF, copy and print.
- Screen recording to MP4, colour picker, screen ruler and OCR.
- System tray, floating toolbar, global hotkeys and single-instance command line.

[0.4.1]: https://github.com/firexsantos/raja-capture/releases/tag/v0.4.1
[0.4.0]: https://github.com/firexsantos/raja-capture/releases/tag/v0.4.0
[0.3.0]: https://github.com/firexsantos/raja-capture/releases/tag/v0.3.0
[0.2.0]: https://github.com/firexsantos/raja-capture/releases/tag/v0.2.0
[0.1.0]: https://github.com/firexsantos/raja-capture/commit/3fa7817
