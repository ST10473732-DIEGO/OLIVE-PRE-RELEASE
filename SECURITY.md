# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| OLIVE 1.0.x (once released; prepared on `release/olive-1.0`) | Yes |
| Earlier OLIVE / DMDO 3.x source snapshots | No |

Security fixes are made on the current release line.

## Reporting a vulnerability

Report vulnerabilities **privately**. Do not open a public issue, discussion or
pull request, and do not post details publicly, until a fix has been released.

> **TODO (owner decision, required before any public release):** choose the private
> reporting channel, for example a dedicated security email address or GitHub
> private vulnerability reporting on the public release repository, and replace
> this note with it.

Until that channel exists, report privately to the maintainer through the channel
you already use to reach them.

Please include:

- the OLIVE version or commit, platform and how OLIVE was installed or run;
- the affected component (see Scope);
- steps to reproduce and the impact you observed;
- whether the issue is already known to anyone else.

Do **not** include, in a report or anywhere public:

- credentials, tokens, API keys or vault contents;
- pairing codes, device identity keys or certificates, Connect World route secrets
  or relay credentials;
- real chats, documents, Notes, Draw content, mail or personal records;
- logs or screenshots that show any of the above.

Use synthetic data and redact identifiers. If sensitive material is essential to
the report, say so and wait to agree a safe way to share it.

## Scope

In scope:

- **OLIVE Connect:** device identities and pairing, pinned TLS transport, the
  per-device permission model (Remote AI, sync, files, Studio, Notes, Draw), file
  transfer and the remote Chat, inference and Studio protocols.
- **Connect World:** the `olive-world/1` relay protocol, route credentials and
  provisioning, Direct/World path selection, and the reference relay in
  `world-relay/`.
- **Credential vault use:** how OLIVE stores and reads secrets in Windows
  Credential Manager, the Linux Secret Service and the iPhone Keychain.
- **Local services:** the Python bridge, loopback-only services and their
  enforcement (ComfyUI, VoiceStudio, previews, Ollama connections), the Electron
  renderer sandbox and IPC, Owner Mode and desktop-control authorisation.
- The iPhone companion app.

Out of scope:

- Vulnerabilities in third-party software (Ollama, ComfyUI, Electron, Python
  packages, models). Report those upstream; tell us if OLIVE's use of them makes
  the issue worse.
- The security of a server you operate for your own relay, beyond the reference
  configuration in `world-relay/`.
- Model output content on its own, without a security impact such as bypassing a
  permission or exfiltrating data.
- Attacks that need an already compromised operating-system account or device.

## Disclosure

We will work with you on a fix and a disclosure date. Please keep exploit details
private until the fix is released and users have had a reasonable time to update.
Public write-ups after that are welcome; credit is given if you want it.
