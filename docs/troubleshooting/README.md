# Troubleshooting

This page covers states OLIVE reports today. Fuller guides will be written with
the installers.

| What you see | What it means | What to do |
| --- | --- | --- |
| "Ollama unavailable. Start Ollama and refresh Models" | OLIVE cannot reach the Ollama server | Start Ollama (Linux source runs start an OLIVE-managed Ollama when one is installed), then refresh Models |
| A Chat mode shows **Needs setup** | Its model or media engine is not installed or not configured | Install the model in Ollama, or configure the media engine. OLIVE never downloads it for you ([chat modes](../features/chat-modes.md)) |
| "Secure credential storage is unavailable or locked. Unlock the desktop keyring and retry. No plaintext fallback was used." | Linux: no unlocked Secret Service (KWallet or GNOME Keyring). Connect identity, Connect World, Mail and Discord need it | Unlock or install a Secret Service provider and retry. On macOS there is no vault backend yet ([install status](../install/README.md)) |
| "The secure device key is unavailable…" | The Connect identity key cannot be read from the vault | Unlock the credential store. OLIVE never replaces an existing key automatically |
| The phone shows **Offline** or will not connect on Wi-Fi | Connect is off, the wrong interface is selected, or a firewall blocks the Connect port | Turn Connect on with the right local interface in Devices; allow the port on the local network |
| Away from home the phone cannot reach the computer | No relay configured, or the phone was never provisioned for World | Configure your relay in Devices › This computer › OLIVE Connect World, then provision the phone on the home network first ([Connect World](../connect-world/README.md)) |

Report security problems privately as described in [SECURITY.md](../../SECURITY.md).
