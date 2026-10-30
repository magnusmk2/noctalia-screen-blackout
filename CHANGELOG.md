# Changelog

## 1.4.14 — match the Startup Manager panel frame

- Apply the Startup Manager's rounded surface and outline to the Screen
  Blackout card, center the monitor map, and keep the panel backdrop
  transparent. Reserve space for the recovery hint inside the card.

## 1.4.13 — restore all screens after right-click focus

- Right-clicking the focused display again now clears every blackout layer,
  including screens that were already black before focusing that display.
- Clarify the revert behavior in the picker and usage documentation.

## 1.4.12 — public repository preparation

- Package the existing 1.4.11 plugin in a source-repository layout.
- Add a per-user build/install/uninstall workflow with guarded replacement.
- Make build tool and protocol locations portable through PATH and pkg-config.
- Document runtime requirements, recovery, input behavior and privacy.
- Include original-code licensing, protocol attribution, CI, source releases,
  publication checks and packaging regression tests.

## 1.4.11 — optimisation baseline

- Poll Hyprland through its local socket without launching child commands.
- Scale an opaque one-pixel buffer with the stable Wayland viewporter protocol.
- Wait for Wayland/shutdown events without periodic layer polling.
- Serialize commands and watcher teardown; write state atomically.
- Keep recovery independent of successful monitor queries and use Linux pidfds.
- Preserve cursor timeout changes and ignore stale picker refresh replies.

Earlier local iterations established monitor selection, right-click focus and
revert, batch blackout, recovery above all overlays, input shielding and the
compact hover picker.
