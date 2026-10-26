#!/usr/bin/env bash
set -euo pipefail

plugin_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
build_dir="$plugin_dir/.build"
compiler="${CC:-cc}"
for tool in "$compiler" wayland-scanner pkg-config; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Missing build tool: %s\n' "$tool" >&2
    exit 1
  fi
done
protocol_dir="$(pkg-config --variable=pkgdatadir wayland-protocols)"
if [[ -z "$protocol_dir" ]]; then
  printf 'Install the wayland-protocols development package.\n' >&2
  exit 1
fi
read -r -a client_cflags <<< "$(pkg-config --cflags wayland-client)"
read -r -a client_libs <<< "$(pkg-config --libs wayland-client)"
read -r -a extra_cflags <<< "${CFLAGS:-}"
read -r -a extra_ldflags <<< "${LDFLAGS:-}"
mkdir -p "$build_dir"

wayland-scanner client-header \
  "$plugin_dir/wlr-layer-shell-unstable-v1.xml" \
  "$build_dir/wlr-layer-shell-unstable-v1-client-protocol.h"
wayland-scanner private-code \
  "$plugin_dir/wlr-layer-shell-unstable-v1.xml" \
  "$build_dir/wlr-layer-shell-unstable-v1-protocol.c"
wayland-scanner private-code \
  "$protocol_dir/stable/xdg-shell/xdg-shell.xml" \
  "$build_dir/xdg-shell-protocol.c"
wayland-scanner client-header \
  "$protocol_dir/stable/viewporter/viewporter.xml" \
  "$build_dir/viewporter-client-protocol.h"
wayland-scanner private-code \
  "$protocol_dir/stable/viewporter/viewporter.xml" \
  "$build_dir/viewporter-protocol.c"

helper_tmp="$(mktemp "$plugin_dir/.blackout-layer.XXXXXX")"
trap 'rm -f -- "$helper_tmp"' EXIT
"$compiler" -O2 -Wall -Wextra "${extra_cflags[@]}" "${client_cflags[@]}" \
  -I"$build_dir" \
  "$plugin_dir/blackout-layer.c" \
  "$build_dir/wlr-layer-shell-unstable-v1-protocol.c" \
  "$build_dir/xdg-shell-protocol.c" \
  "$build_dir/viewporter-protocol.c" \
  "${extra_ldflags[@]}" -o "$helper_tmp" "${client_libs[@]}"
chmod 0755 "$helper_tmp"
mv -f -- "$helper_tmp" "$plugin_dir/blackout-layer"
