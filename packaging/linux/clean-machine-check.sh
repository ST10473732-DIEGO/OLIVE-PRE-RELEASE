#!/usr/bin/env bash
# OLIVE 1.0 clean-machine acceptance helper (Linux). Read-only except for the results file and
# the throwaway HOME of `sandbox`. It never installs packages, changes AppArmor/SELinux or
# sysctls, or touches an existing OLIVE profile. See docs/install/linux-clean-machine-acceptance.md.
#
#   clean-machine-check.sh facts                       record OS / FUSE / sandbox / GPU facts
#   clean-machine-check.sh verify <AppImage> <sha256>  checksum must print MATCH
#   clean-machine-check.sh sandbox                     report OLIVE processes started with --no-sandbox
#   clean-machine-check.sh leftovers                   list paths OLIVE may leave after removal
set -uo pipefail

distro() { . /etc/os-release 2>/dev/null; echo "${ID:-unknown}-${VERSION_ID:-unknown}"; }
RESULTS="results-$(distro).md"

note() { printf '%s\n' "$*" | tee -a "$RESULTS"; }

facts() {
  [ -f "$RESULTS" ] || printf '# OLIVE 1.0 clean-machine results: %s\n\n' "$(distro)" >"$RESULTS"
  note "## Facts ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  note '```'
  note "os: $(. /etc/os-release; echo "$PRETTY_NAME")"
  note "kernel: $(uname -r)"
  note "glibc: $(ldd --version 2>/dev/null | head -1)"
  note "desktop: ${XDG_CURRENT_DESKTOP:-?} session: ${XDG_SESSION_TYPE:-?}"
  note "libfuse.so.2: $( (ldconfig -p 2>/dev/null | grep -q 'libfuse.so.2') && echo present || echo MISSING)"
  note "fusermount: $(command -v fusermount || echo -) fusermount3: $(command -v fusermount3 || echo -)"
  note "unshare -Ur true: $(unshare -Ur true 2>/dev/null && echo allowed || echo DENIED)"
  for f in /proc/sys/kernel/unprivileged_userns_clone /proc/sys/user/max_user_namespaces \
           /proc/sys/kernel/apparmor_restrict_unprivileged_userns; do
    [ -r "$f" ] && note "$(basename "$f"): $(cat "$f")"
  done
  note "selinux: $(getenforce 2>/dev/null || echo n/a)"
  note "gpu: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || lspci 2>/dev/null | grep -iE 'vga|3d' | head -2 | tr '\n' ';' || echo unknown)"
  note "ram: $(free -h | awk '/^Mem:/{print $2}')"
  note "free in ~/.local/share: $(df -h --output=avail "$HOME/.local/share" 2>/dev/null | tail -1 | tr -d ' ')"
  note "existing profiles: $(ls -d "$HOME/.local/share/olive" "$HOME/.olive" "$HOME/.dmdo" 2>/dev/null | tr '\n' ' ' || true)"
  note '```'
}

verify() {
  local file="$1" expected="$2" actual
  actual=$(sha256sum "$file" | cut -d' ' -f1)
  if [ "$actual" = "$expected" ]; then note "verify $(basename "$file"): MATCH $actual"; else note "verify $(basename "$file"): MISMATCH $actual (expected $expected)"; return 1; fi
}

sandbox() {
  local main renderers unsandboxed
  main=$(pgrep -af '(/|^)olive( |$)' | grep -v -- '--type=' | head -1)
  renderers=$(pgrep -af -- '--type=renderer' | grep -c '/olive' || true)
  unsandboxed=$(pgrep -af -- '--type=renderer' | grep '/olive' | grep -c -- '--no-sandbox' || true)
  note "sandbox: main=${main:-<not running>}"
  note "sandbox: renderers=$renderers renderers-with---no-sandbox=$unsandboxed (must be 0)"
  [ "${unsandboxed:-0}" = 0 ]
}

leftovers() {
  note "## Leftovers ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  for p in "$HOME/.local/share/olive" "${XDG_CONFIG_HOME:-$HOME/.config}/olive" "$HOME/.cache/olive" \
           "$HOME/.local/share/applications/olive.desktop" "$HOME/.local/share/applications/local.dmdo.desktop.desktop" \
           "${XDG_CONFIG_HOME:-$HOME/.config}"/autostart/*olive* "${XDG_CONFIG_HOME:-$HOME/.config}"/autostart/*dmdo* \
           "$HOME/.olive" "$HOME/.dmdo"; do
    [ -e "$p" ] && note "present: $p ($(du -sh "$p" 2>/dev/null | cut -f1))"
  done
  note "(end of leftovers)"
}

case "${1:-}" in
  facts) facts ;;
  verify) verify "${2:?AppImage}" "${3:?sha256}" ;;
  sandbox) sandbox ;;
  leftovers) leftovers ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
