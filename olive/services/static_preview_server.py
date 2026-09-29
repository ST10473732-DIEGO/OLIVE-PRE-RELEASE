"""OLIVE-owned static preview server for a workspace folder.

Run as a script by the Studio run service (never imported by the backend):

    python static_preview_server.py <root> <port>

It binds 127.0.0.1 only, serves regular files inside <root>, refuses hidden
paths (.git, .env, ...), symlinks that leave the root and directory listings,
and sends no-cache headers so edits appear on refresh. It depends only on the
standard library, so any local Python can run it.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit


def handler_for(root: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def _allowed(self):
            path = unquote(urlsplit(self.path).path)
            parts = [p for p in path.split("/") if p]
            if any(p.startswith(".") for p in parts):
                return False
            target = (root / Path(*parts)).resolve() if parts else root
            if target != root and root not in target.parents:
                return False
            if target.is_dir():
                return (target / "index.html").is_file()
            return target.is_file()

        def send_head(self):
            if not self._allowed():
                self.send_error(404, "Not found")
                return None
            return super().send_head()

        def list_directory(self, path):
            self.send_error(404, "Not found")
            return None

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def log_message(self, format, *args):
            sys.stderr.write("%s %s\n" % (self.command if hasattr(self, "command") else "-", format % args))

    return Handler


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: static_preview_server.py <root> <port>")
    root = Path(argv[1]).resolve(strict=True)
    port = int(argv[2])
    if not root.is_dir() or not 1024 <= port <= 65535:
        raise SystemExit("invalid root or port")
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(root))
    print(f"OLIVE static preview on http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main(sys.argv)
