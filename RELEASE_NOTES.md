# Git Archive Generator v4.1.0

## Added

- HTTPS repository source with automatic bare Git caching. Archive by date, SHA range, single commit, or tag without manually cloning a working folder.
- Private repository authentication through personal access tokens, existing Git credentials, or browser login with Git Credential Manager.
- Exclude start commit checkbox for SHA ranges, including matching preview, archive contents, changelog, and history.
- Copy an eight-character SHA from the range fields or commit picker.
- New archive/Git application icon for macOS and Windows.

## Improved

- Compact rounded buttons and fields, consistent light/dark colors, and clear separation between local folder and HTTPS forms.
- Authentication fields appear only for personal access token mode.
- macOS trackpad scrolling and native runtime Dock icon.
- Long Git Pull output is scrollable with a permanently visible OK button.

## Fixed

- History now uses a stable per-user data directory, atomic writes, and successful completion events instead of progress bar timing.
- Legacy history migration, saved exclude-start settings, and remote URL history.
- Rounded button corners remain rounded on hover, press, focus, and disabled states.
- Windows build script no longer depends on a missing spec file.

## Downloads

- **macOS Apple Silicon:** `GitArchiveGenerator-macos-arm64.zip`. Extract and open `GitArchiveGenerator.app`.
- **Windows:** `GitArchiveGenerator-windows.exe`.
- **Linux:** `GitArchiveGenerator-linux`.

Git must be installed on the computer. PAT authentication works without existing credentials, including accounts with 2FA. Tokens are not saved by the app. Web login requires Git Credential Manager; enterprise servers may require OAuth/SSO setup. Company repositories require network/VPN access and trusted certificates. LFS payloads and submodules are not downloaded automatically.

The macOS app is signed ad hoc, without Apple notarization. If macOS blocks opening it, use System Settings → Privacy & Security → Open Anyway for this downloaded app.

## Validation

19 automated tests cover ranges, archives, history, cache updates, URL validation, and real private HTTPS token authentication without credential helpers. GUI checks cover both themes, compact rounded controls, source switching, and authentication field visibility on macOS. Windows/Linux builds and tests run in GitHub Actions.
