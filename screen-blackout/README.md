# Screen Blackout

Cover selected Hyprland monitors with a solid black input-shielding layer.
The compact picker reflects the current monitor layout and keeps recovery
controls above the blackout surfaces.

| Plugin | Value |
| --- | --- |
| ID | `magnus/screen-blackout` |
| Bar entry | `magnus/screen-blackout:toggle` |
| Panel entry | `magnus/screen-blackout:picker` |
| Required Noctalia API | `34` |
| Runtime commands | `python3`, `sleep`, and the Noctalia host |

## Requirements and installation

Requires Noctalia 5.3+, a Hyprland 0.55+ Lua-config session, Python 3.11+, Linux
pidfd/signalfd support, and a locally built `blackout-layer` helper. Building
requires Bash, a C compiler, pkg-config, wayland-scanner, Wayland client headers,
and wayland-protocols. The helper uses layer-shell and stable viewporter.

Use the repository's `install.sh`, which builds and installs a per-user copy.
A remote Git source does not build the native helper automatically. Full build,
install, uninstall, privacy and recovery instructions are in the repository
[README](../README.md). This is an independent community project.

## Usage

Enable `magnus/screen-blackout` and add `magnus/screen-blackout:toggle` to a bar.
Hover the bar icon, then move into the picker. Left-click a display to toggle
it. Right-click a display to black out the others; right-click the same display
again to restore the previous state. Batch controls cover or restore all outputs.

The panel can also be opened with:

```sh
noctalia msg panel-toggle magnus/screen-blackout:picker
```

Configure a separate recovery shortcut before blanking all displays. For a
default per-user install, the recovery command is:

```sh
python3 ~/.local/share/noctalia/plugins/magnus-screen-blackout/blackout.py restore-all
```

## Behavior and diagnostics

The overlay shields underlying apps from pointer/touch input and does not take
keyboard focus. It keeps displays powered and connected. The cursor hides
after one second of inactivity over a blacked-out output and retains the user's
prior inactivity timeout over visible outputs. Use a session locker for access
control and authentication.

Only local Wayland/Hyprland Unix sockets are used; there is no telemetry or
internet access. Runtime PID/state files and logs are under
`$XDG_RUNTIME_DIR/noctalia-screen-blackout/`. Do not publish complete logs or
configuration files without reviewing and redacting them.

The helper submits one opaque pixel scaled to the full output and waits for
Wayland/shutdown events. The Python watcher checks cursor position every 200 ms
and geometry every second without launching polling subprocesses.

Run this plugin's regression checks from its directory:

```sh
python3 -B -m unittest discover -s tests -v
```

## Licence

Original code uses the included [MIT licence](LICENSE). Protocol copyright and
permission terms are retained in [third-party notices](THIRD_PARTY_NOTICES.md).
