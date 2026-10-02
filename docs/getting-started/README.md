# Getting started

OLIVE is a private AI assistant that runs on your own computer. Chat, documents,
coding, Notes, Draw, images, speech and video are processed locally. Text models
run in [Ollama](https://ollama.com); media runs in local engines (ComfyUI,
VoiceStudio). There is no OLIVE account, no hosted AI and no telemetry.

The iPhone app is a companion: it sends your requests to your paired computer,
which does the work, and shows the results.

## What leaves your computer

OLIVE uses the internet only when you use a feature that needs it:

| Feature | What goes out |
| --- | --- |
| NOW and web research | Search queries and the pages fetched for them. Answers are written locally |
| Mail, Discord, Google sign-in | Traffic to the services you connect, only when configured |
| Connect World | Encrypted Connect traffic through a relay **you** choose. The relay cannot read content but sees connection metadata (addresses, timing, sizes) |
| Model downloads | Only when you download a model yourself; OLIVE never downloads one automatically |

The profile on disk is not encrypted by OLIVE; secrets go to the operating
system's credential store ([credentials](../security/credentials.md)).

## Status of OLIVE 1.0

OLIVE 1.0 installers and first-run model setup are still being prepared. Until
they exist, OLIVE runs from a source checkout: see [install](../install/README.md)
and [development](../development/README.md).

Next: [Chat modes](../features/chat-modes.md) · [iPhone](../mobile/README.md) ·
[Connect World](../connect-world/README.md).
