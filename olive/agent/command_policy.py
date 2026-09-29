"""Conservative classification of command text for the permission engine.

Classification only ADDS permission checks (terminal.admin, software.install,
system.settings); it never removes one. Unknown commands keep the ordinary
terminal.execute policy. Shell metacharacters that chain or substitute
commands make the whole command at least as sensitive as its worst part.
"""
import re
import shlex

WORKSPACE = "workspace"
PACKAGE_INSTALL = "package_install"
NETWORK_SERVICE = "network_service"
SYSTEM = "system"
PRIVILEGED = "privileged"
ORDER = (WORKSPACE, NETWORK_SERVICE, PACKAGE_INSTALL, SYSTEM, PRIVILEGED)

_PRIVILEGED = {"sudo", "su", "doas", "pkexec", "runas", "gsudo"}
_SYSTEM_PACKAGE = {"pacman", "yay", "paru", "apt", "apt-get", "dpkg", "dnf", "yum", "zypper", "rpm", "snap", "flatpak",
                   "brew", "winget", "choco", "scoop", "emerge", "apk"}
_SYSTEM = {"systemctl", "modprobe", "insmod", "rmmod", "mkfs", "fdisk", "parted", "mount", "umount", "dd", "chown",
           "shutdown", "reboot", "poweroff", "sysctl", "iptables", "nft", "ufw", "firewall-cmd", "useradd", "usermod",
           "passwd", "visudo", "crontab", "bcdedit", "diskpart", "reg", "netsh", "sc"}
_PROJECT_INSTALL = {("npm", "install"), ("npm", "i"), ("npm", "add"), ("pnpm", "add"), ("pnpm", "install"),
                    ("yarn", "add"), ("pip", "install"), ("pip3", "install"), ("uv", "add"), ("uv", "pip"),
                    ("dotnet", "add"), ("dotnet", "tool"), ("cargo", "add"), ("cargo", "install"), ("go", "install"),
                    ("go", "get"), ("gem", "install"), ("composer", "require"), ("npx", "")}
_SERVE = {("python", "-m"), ("python3", "-m"), ("npm", "start"), ("npm", "run"), ("dotnet", "run"), ("node", ""),
          ("flask", "run"), ("uvicorn", ""), ("php", "-S")}
_CHAIN = re.compile(r"[;&|`\n]|\$\(|>\s*/|<\(")


def _segments(command: str):
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    segment = []
    for token in tokens:
        if token in {";", "&&", "||", "|", "&"}:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def classify(command) -> str:
    """Return the most sensitive class found in a command string or argv list."""
    text = " ".join(command) if isinstance(command, (list, tuple)) else str(command or "")
    worst = WORKSPACE
    def raise_to(level):
        nonlocal worst
        if ORDER.index(level) > ORDER.index(worst):
            worst = level
    for segment in _segments(text):
        names = [s.rsplit("/", 1)[-1].casefold().removesuffix(".exe") for s in segment]
        head = names[0] if names else ""
        second = names[1] if len(names) > 1 else ""
        if head in _PRIVILEGED or "sudo" in names:
            raise_to(PRIVILEGED)
        elif head in _SYSTEM_PACKAGE:
            raise_to(SYSTEM)
        elif head in _SYSTEM:
            if head == "systemctl" and "--user" in names:
                raise_to(NETWORK_SERVICE)
            else:
                raise_to(SYSTEM)
        elif head == "chmod" and any(s.startswith(("/", "~")) and not s.startswith("./") for s in segment[1:]):
            raise_to(SYSTEM)
        elif (head, second) in _PROJECT_INSTALL or (head, "") in _PROJECT_INSTALL:
            if "-g" in names or "--global" in names or "--system" in names or "--user" in names:
                raise_to(SYSTEM)
            else:
                raise_to(PACKAGE_INSTALL)
        elif head in {"npm", "pnpm", "yarn"} and second == "run":
            if len(names) > 2 and names[2] in {"dev", "start", "serve", "preview"}:
                raise_to(NETWORK_SERVICE)
        elif (head, second) in _SERVE or (head, "") in _SERVE:
            raise_to(NETWORK_SERVICE)
        elif head in {"curl", "wget"} and any(s in {"|", "-o", "-O", "--output"} for s in segment):
            raise_to(PACKAGE_INSTALL)
    if re.search(r"\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba|z|fi)?sh\b", text):
        raise_to(PRIVILEGED)
    # Substitutions and quoting can hide a privileged program from tokenisation.
    if re.search(r"(?:^|[\s;&|`($'\"])(?:sudo|su|doas|pkexec|runas|gsudo)(?=$|[\s;&|`)'\"])", text):
        raise_to(PRIVILEGED)
    if _CHAIN.search(text) and worst == WORKSPACE and re.search(r"\b(?:rm|mv|cp|chmod|kill|pkill)\b", text):
        raise_to(SYSTEM)
    return worst


def extra_permissions(command) -> tuple[str, ...]:
    level = classify(command)
    return {PRIVILEGED: ("terminal.admin",), SYSTEM: ("terminal.admin", "system.settings"),
            PACKAGE_INSTALL: ("software.install",)}.get(level, ())
