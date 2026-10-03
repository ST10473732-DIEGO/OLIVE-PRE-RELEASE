# Linux clean-machine acceptance (OLIVE 1.0)

Status: **prepared, not run.** None of the distributions below is validated yet. The AppImage
has been built and launched only on the CachyOS reference machine, in an isolated profile.

Targets (fresh install, default desktop, a normal non-root user, all updates applied):

| Distribution | Desktop | Notes |
| --- | --- | --- |
| Ubuntu 24.04 LTS | GNOME (Wayland) | AppArmor restricts unprivileged user namespaces; FUSE 3 only by default |
| Fedora (current supported release) | GNOME (Wayland) | SELinux enforcing; `fuse` (v2) may be missing |
| Debian (current stable) | GNOME or KDE | User namespaces normally allowed; `libfuse2` may be missing |

Use one machine (or VM with GPU pass-through for Creator) per distribution. Record every
result in `results-<distro>.md`, which `clean-machine-check.sh` starts for you.

## 0. Before you start

- Copy `OLIVE-1.0.0.AppImage`, its `SHA256SUMS` line and
  `packaging/linux/clean-machine-check.sh` to the machine.
- `bash clean-machine-check.sh facts` records the OS, kernel, glibc, FUSE, user-namespace,
  AppArmor/SELinux, GPU and driver facts, plus free disk space.
- `bash clean-machine-check.sh verify OLIVE-1.0.0.AppImage <sha256>` must print `MATCH`.

## 1. AppImage and FUSE

| # | Step | Expected |
| --- | --- | --- |
| 1.1 | `chmod +x OLIVE-1.0.0.AppImage && ./OLIVE-1.0.0.AppImage` without `libfuse2` | The AppImage runtime prints its FUSE message and exits. OLIVE does not start half-way |
| 1.2 | `APPIMAGE_EXTRACT_AND_RUN=1 ./OLIVE-1.0.0.AppImage` | Starts (subject to §2) |
| 1.3 | Install the FUSE 2 package (`libfuse2t64` / `fuse` / `libfuse2`), run again | Starts through the mount |

## 2. Chromium sandbox (must fail closed)

| # | Step | Expected |
| --- | --- | --- |
| 2.1 | Ubuntu, default AppArmor policy: run the AppImage | "OLIVE could not start safely" dialog with the Ubuntu instructions. Exit status 78 once it is dismissed. No backend process is left |
| 2.2 | Ubuntu: follow `docs/install/linux.md` (extract, AppArmor profile, run `olive` directly) | Starts with the sandbox. `bash clean-machine-check.sh sandbox` shows no renderer with `--no-sandbox` |
| 2.3 | Fedora / Debian: run the AppImage | Starts with the sandbox (user namespaces allowed). Same check |
| 2.4 | `./OLIVE-1.0.0.AppImage --no-sandbox` | Refused, as in 2.1 |

## 3. First launch

| # | Step | Expected |
| --- | --- | --- |
| 3.1 | First start | The setup wizard opens. The profile is created at `~/.local/share/olive`. Nothing is written to `~/.dmdo` or `~/.olive` |
| 3.2 | App menu / dock | Entry and window are "OLIVE" with the OLIVE icon (`olive.desktop`, `StartupWMClass=olive`) |
| 3.3 | Wizard → System check | Reports the real RAM, VRAM, disk and GPU. No error banner |

## 4. Core planning (no download yet)

| # | Step | Expected |
| --- | --- | --- |
| 4.1 | Wizard → Core | Offers Linux Ollama 0.34.2, qwen3:8b, gpt-oss:20b, qwen3.5:9b and qwen3-embedding:0.6b, with sizes |
| 4.2 | Same screen | Windows Ollama, qwen3-vl:8b, qwen3-coder:30b, Playwright, FLUX.2 [klein] 4B, Creator runtimes, LTX, VoiceStudio, MAX and UNCENSORED are not offered for download (unavailable or "not yet available in this build") |
| 4.3 | Space check | The plan compares the bytes needed against the filesystem that holds `~/.local/share/olive` |

## 5. Core real download

| # | Step | Expected |
| --- | --- | --- |
| 5.1 | Install Core | Ollama is downloaded from `github.com`/`objects.githubusercontent.com` and verified. Models are pulled through it. Progress moves |
| 5.2 | Interrupt the network for 30 s mid-download | The download resumes and is not restarted from zero |
| 5.3 | Completion | Chat answers with qwen3:8b. `runtimes.json` lists `ollama` as `olive-owned` |
| 5.4 | Document attach (a small PDF) | Indexed with qwen3-embedding. The answer cites the document by name |

## 6. Restart

| # | Step | Expected |
| --- | --- | --- |
| 6.1 | Quit and start again | No wizard. Chat history is kept. Ollama starts on demand |
| 6.2 | Reboot, then start | Same as 6.1 |
| 6.3 | Launch at login on, then log out and in | OLIVE starts from the AppImage path (`$APPIMAGE`), not from `/tmp/.mount_*` |

## 7. Uninstall

| # | Step | Expected |
| --- | --- | --- |
| 7.1 | Settings → remove Core components | Ollama runtime and models removed. `runtimes.json` entries are forgotten |
| 7.2 | Delete the AppImage | `bash clean-machine-check.sh leftovers` lists only the profile (`~/.local/share/olive`), the config, the optional `local.dmdo.desktop.desktop` and any autostart entry, each documented |
| 7.3 | Remove those paths | Nothing else that OLIVE wrote remains |

## 8. Connect

| # | Step | Expected |
| --- | --- | --- |
| 8.1 | Pair the iPhone on the same network | Pairing succeeds. A loopback address is never offered |
| 8.2 | Connect World (relay) from another network | Chat reaches the desktop through the relay. Remote AI stays text-only |

## 9. Creator (where an NVIDIA GPU exists)

Creator runtimes are not offered in 1.0 until the owner approves them.

| # | Step | Expected |
| --- | --- | --- |
| 9.1 | REIMAGINE preset without Creator installed | "Needs setup". No download is attempted |
| 9.2 | (Only after an owner-approved Creator build exists) install and run one REIMAGINE generate + edit | Image produced. GPU memory released afterwards |

## Sign-off

A distribution counts as validated only when every row above has a recorded result
(pass, or a documented and accepted exception) in its `results-<distro>.md`.
