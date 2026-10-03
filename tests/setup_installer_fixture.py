"""Local fixture servers for first-run setup tests: no real network, no real models.

FileServer   serves bytes over loopback http:// with honest Range support (and knobs to
             misbehave: drop connections, ignore ranges, redirect elsewhere).
FakeOllama   a tiny Ollama API (/api/tags, /api/pull streaming, /api/delete, /api/generate)
             plus a registry (/v2/<name>/manifests/<tag>) whose manifests have known digests.
"""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import tarfile
import threading
import time
import zipfile


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass  # Clients dropping connections (cancel tests) are expected.


class FileServer:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.redirects: dict[str, str] = {}
        self.drop_after: dict[str, int] = {}  # path -> bytes to send before dropping the first response
        self.ignore_range = False
        self.extra = b''  # appended to full-body responses (oversize attack)
        self.requests: list[tuple[str, str | None]] = []
        self.slow = 0.0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append((self.path, self.headers.get('Range')))
                if self.path in outer.redirects:
                    self.send_response(302)
                    self.send_header('Location', outer.redirects[self.path])
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                body = outer.files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                header = self.headers.get('Range')
                if header and not outer.ignore_range:
                    start, end = header.split('=', 1)[1].split('-')
                    start, end = int(start), min(int(end), len(body) - 1)
                    chunk = body[start:end + 1]
                    self.send_response(206)
                    self.send_header('Content-Range', f'bytes {start}-{end}/{len(body)}')
                else:
                    chunk = body + outer.extra
                    self.send_response(200)
                self.send_header('Content-Length', str(len(chunk)))
                self.end_headers()
                drop = outer.drop_after.pop(self.path, None)
                if drop is not None:
                    self.wfile.write(chunk[:drop])
                    self.wfile.flush()
                    self.close_connection = True
                    try:
                        self.connection.shutdown(2)
                    except OSError:
                        pass
                    return
                for i in range(0, len(chunk), 65536):
                    self.wfile.write(chunk[i:i + 65536])
                    if outer.slow:
                        time.sleep(outer.slow)

        self.server = _Server(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}'

    def add(self, path, body: bytes) -> str:
        self.files[path] = body
        return self.base + path

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def registry_manifest(name: str, size: int) -> bytes:
    """A registry manifest document for a fake model; its sha256 is the model's digest."""
    digest = hashlib.sha256(name.encode()).hexdigest()
    return json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
                       'config': {'digest': 'sha256:' + hashlib.sha256(b'config' + name.encode()).hexdigest(), 'size': 10},
                       'layers': [{'mediaType': 'application/vnd.ollama.image.model', 'digest': 'sha256:' + digest,
                                   'size': size - 10}]}).encode()


class FakeOllama:
    def __init__(self):
        self.models: dict[str, str] = {}  # name -> digest
        self.registry: dict[str, bytes] = {}  # '/v2/library/x/manifests/tag' -> bytes
        self.paths: dict[str, str] = {}  # model -> registry path
        self.serve_digest: dict[str, str] = {}  # what a pull installs (defaults to the registry digest)
        self.pull_error: str | None = None
        self.pull_delay = 0.0
        self.pulls: list[str] = []
        self.deleted: list[str] = []
        self.generated: list[str] = []
        self.answer = 'ready'
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _json(self, value, status=200):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                length = int(self.headers.get('Content-Length') or 0)
                return json.loads(self.rfile.read(length) or b'{}')

            def do_GET(self):
                if self.path == '/api/tags':
                    return self._json({'models': [{
                        'name': n, 'model': n, 'digest': d, 'size': 500, 'modified_at': '2026-10-03T00:00:00Z',
                        'details': {'format': 'gguf', 'family': 'fixture', 'families': ['fixture'],
                                    'parameter_size': '1B', 'quantization_level': 'Q4_K_M'}}
                        for n, d in outer.models.items()]})
                if self.path == '/api/version':
                    return self._json({'version': '0.0.0-fixture'})
                if self.path in outer.registry:
                    body = outer.registry[self.path]
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._json({'error': 'not found'}, 404)

            def do_DELETE(self):
                if self.path == '/api/delete':
                    model = self._body().get('model')
                    outer.deleted.append(model)
                    outer.models.pop(model, None)
                    return self._json({})
                self._json({'error': 'not found'}, 404)

            def do_POST(self):
                if self.path == '/api/show':
                    model = self._body().get('model')
                    if model not in outer.models:
                        return self._json({'error': 'model not found'}, 404)
                    embedding = 'embedding' in model
                    return self._json({'capabilities': ['embedding'] if embedding else ['completion'],
                                       'model_info': {'general.architecture': 'fixture', 'fixture.context_length': 8192},
                                       'details': {'format': 'gguf', 'family': 'fixture'}, 'modelfile': '',
                                       'parameters': '', 'template': ''})
                if self.path == '/api/generate':
                    request = self._body()
                    outer.generated.append(request.get('model'))
                    if request.get('model') not in outer.models:
                        return self._json({'error': 'model not found'}, 404)
                    return self._json({'response': outer.answer, 'done': True})
                if self.path != '/api/pull':
                    return self._json({'error': 'not found'}, 404)
                model = self._body()['model']
                outer.pulls.append(model)
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-ndjson')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()

                def send(event):
                    data = (json.dumps(event) + '\n').encode()
                    try:
                        self.wfile.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
                        self.wfile.flush()
                        return True
                    except OSError:
                        return False
                if outer.pull_error:
                    send({'error': outer.pull_error})
                else:
                    send({'status': 'pulling manifest'})
                    for step in range(1, 6):
                        if not send({'status': 'pulling', 'digest': 'sha256:abc', 'total': 500, 'completed': step * 100}):
                            return
                        time.sleep(outer.pull_delay)
                    digest = outer.serve_digest.get(model) or hashlib.sha256(
                        outer.registry.get(outer.paths.get(model, ''), b'')).hexdigest()
                    outer.models[model] = digest
                    send({'status': 'success'})
                try:
                    self.wfile.write(b'0\r\n\r\n')
                except OSError:
                    pass

        self.server = _Server(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}'

    def publish(self, model: str, size: int) -> tuple[str, str]:
        """Put a model in the fake registry; returns (manifest url, digest)."""
        namespace, tag = model.split(':')
        path = f"/v2/{namespace if '/' in namespace else 'library/' + namespace}/manifests/{tag}"
        body = registry_manifest(model, size)
        self.registry[path] = body
        self.paths[model] = path
        return self.base + path, hashlib.sha256(body).hexdigest()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def tar_bytes(members: dict[str, bytes], mode='w:gz', links: dict[str, str] | None = None,
              hardlinks: dict[str, str] | None = None, executable=()) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name in executable else 0o644
            tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
        for name, target in (hardlinks or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.LNKTYPE, target
            tar.addfile(info)
    return buffer.getvalue()


def zip_bytes(members: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)
            bundle.writestr(info, target)
    return buffer.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_manifest(files: FileServer, ollama: FakeOllama, runtime_archive: bytes, *, fast='qwen3:8b',
                     normal='gpt-oss:20b', now='qwen3.5:9b', embedding='qwen3-embedding:0.6b', model_size=500,
                     wheels: dict[str, bytes] | None = None, target='linux-x86_64') -> dict:
    """A complete fixture manifest in the release schema, with loopback sources."""
    from olive.services import runtime_manifest
    release = runtime_manifest.load()
    url = files.add('/ollama-fixture.tar.gz', runtime_archive)
    licence = {'spdx': 'MIT', 'name': 'MIT', 'url': None, 'acceptance_required': False,
               'distribution': 'download-at-first-run', 'reviewed': True}
    entries = [{
        'id': 'fixture-ollama', 'kind': 'archive', 'provides': 'ollama-runtime', 'name': 'Fixture Ollama',
        'version': '0', 'platforms': [target], 'validated_platforms': [target], 'enabled': True,
        'source': {'publisher': 'fixture', 'url': url, 'hosts': ['127.0.0.1']}, 'sha256': sha(runtime_archive),
        'size_bytes': len(runtime_archive),
        'install': {'destination': 'runtime/ollama', 'format': 'tar.gz', 'installed_bytes': 4096,
                    'executables': ['bin/ollama'], 'register': {'runtime': 'ollama', 'paths': {'executable': 'bin/ollama'}}},
        'licence': licence, 'reason': None}]
    for slot, model in (('model-fast', fast), ('model-normal', normal), ('model-now', now), ('model-embedding', embedding)):
        manifest_url, digest = ollama.publish(model, model_size)
        entries.append({'id': 'fixture-' + slot, 'kind': 'ollama-model', 'provides': slot, 'name': model,
                        'version': model, 'platforms': [target], 'validated_platforms': [], 'enabled': True,
                        'source': {'publisher': 'fixture', 'url': manifest_url, 'hosts': ['127.0.0.1']},
                        'ollama': {'model': model, 'manifest_digest': digest}, 'sha256': None, 'size_bytes': model_size,
                        'install': {'destination': 'ollama', 'format': 'ollama'}, 'licence': licence, 'reason': None})
    if wheels:
        listed = [{'name': name, 'url': files.add('/' + name, data), 'sha256': sha(data), 'size_bytes': len(data)}
                  for name, data in wheels.items()]
        entries.append({'id': 'fixture-playwright', 'kind': 'python-wheels', 'provides': 'playwright',
                        'name': 'Fixture Playwright', 'version': '0', 'platforms': [target], 'validated_platforms': [],
                        'enabled': True, 'source': {'publisher': 'fixture', 'url': None, 'hosts': ['127.0.0.1']},
                        'files': {target: listed}, 'sha256': None, 'size_bytes': None,
                        'install': {'destination': 'components/fixture-playwright', 'format': 'wheels',
                                    'installed_bytes': 4096, 'executables': []},
                        'licence': licence, 'reason': None})
    provided = {e['provides'] for e in entries}
    # Keep every release slot so features stay meaningful; unprovided ones are disabled placeholders.
    for entry in release['entries']:
        if entry['provides'] not in provided:
            entries.append({**entry, 'id': 'release-' + entry['id'], 'enabled': False,
                            'reason': entry.get('reason') or 'Not part of the fixture'})
    return {'schema': runtime_manifest.SCHEMA, 'manifest_version': 'fixture', 'product_version': '1.0.0',
            'fixture': True, 'profiles': release['profiles'], 'features': release['features'], 'entries': entries,
            'not_distributable': []}
