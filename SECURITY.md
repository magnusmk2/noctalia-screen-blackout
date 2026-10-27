# Security and privacy

## Supported versions

Security fixes target the latest release. Report the exact version and commit
when possible. Supported runtimes and the tested environment are in README.md.

## Reporting

Use [private vulnerability reporting](https://github.com/magnusmk2/noctalia-screen-blackout/security/advisories/new)
under **Security → Report a vulnerability**. If that option is unavailable, open an
issue asking for a private reporting channel without including exploit details,
credentials, private logs, or personal data. Never post a token or private key.
Do not send private information to an assumed email address.

Private vulnerability reporting is enabled for this repository.

## What the plugin does

The plugin operates as the current user. It creates local Wayland surfaces,
reads display geometry and pointer position through a local Hyprland Unix
socket, temporarily changes the cursor inactivity timeout, and starts/stops
its own helper processes. It writes PID/state files and small diagnostic logs
under the user's runtime directory. It makes no internet requests, sends no
telemetry, and does not store raw pointer-coordinate histories.

Pointer and touch input over a blacked-out display is intercepted. Keyboard
focus and compositor shortcuts continue to work. The overlay provides visual
blanking; use a session locker such as hyprlock for authentication and access
control. Other software may still access the underlying applications.

Configure and verify a Restore All shortcut before using all-monitor blackout.
From another terminal in the same graphical session, recovery is also available
through `blackout.py restore-all`. See README.md for the installation path.

The installer builds reviewed local source and writes only the selected user
data directory. It does not fetch or execute remote scripts, enable the plugin,
modify compositor configuration, or require elevated privileges.

## Contributions affecting security

Changes to process ownership checks, runtime files, input regions, cursor
restoration, subprocess handling, and workflow permissions need regression
checks and clear review. Preserve third-party copyright notices. Do not add
credentials, telemetry, opaque executables, or remote-code bootstrapping.
