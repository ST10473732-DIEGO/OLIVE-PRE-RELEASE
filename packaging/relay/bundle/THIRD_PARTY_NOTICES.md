# OLIVE Connect World relay 1.0.0: third-party notices

The relay code in this bundle uses only the Python standard library. It contains no
third-party source code. Running it needs software that keeps its own licence:

| Component | Where it comes from | Licence |
| --- | --- | --- |
| CPython 3.11 or newer | Your operating system (bundle and systemd use) or the `python:3.12-slim` base image (Docker) | PSF-2.0 (https://docs.python.org/3/license.html), plus the notices of libraries it links (OpenSSL, zlib, libffi, expat, SQLite and others), shipped by the provider of that Python |
| Debian packages in `python:3.12-slim` | Docker Official Image `python`, pinned by digest in the Dockerfile | Each package's licence, in `/usr/share/doc/*/copyright` inside the image |
| Caddy 2 (optional TLS proxy in `compose.yaml`) | Docker Official Image `caddy:2`, pulled separately | Apache-2.0 |
| nginx (optional, `nginx.conf.example`) | Your operating system | BSD-2-Clause |

This bundle does not include or redistribute any of these components. A container image
built from the Dockerfile does include the base image's contents; keep those notices
(they are inside the image) when you distribute such an image.

Flagged for owner/legal review: whether an OLIVE-published relay image (which redistributes
the Debian base and CPython) needs a fuller notice file generated from the image's package
list at build time.
