"""Zero-dependency, loopback-only server for the ProcureFlow local procurement demo.

Usage: python -m demo.server [--port 18881] [--allow-in-memory-writes]
No LLM credentials, Java ERP, MongoDB, external URLs, or sandbox required.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from demo.engine import (
    DemoEngine, DemoInputError, DemoNotFound, DemoWriteDisabled,
    PARTS, SUPPLIERS, INVENTORY,
)


STATIC = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def _business(data):
    return {"code": 200, "message": "synthetic demo", "data": data}


class DemoHandler(BaseHTTPRequestHandler):
    engine = DemoEngine()
    server_version = "ProcureFlowOfflineDemo/0.1"

    def log_message(self, format, *args):
        # Deliberately do not log user prompts, tokens, query strings or bodies.
        return

    def _headers(self, status: int, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        self.send_header("X-Frame-Options", "DENY")

    def _json(self, status: int, payload: object):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_events(self, events: list[dict]):
        self._headers(200, "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in events:
            line = "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
        self.close_connection = True

    def _require_local_host(self) -> bool:
        """Deny DNS-rebinding hostnames and non-loopback Host headers.

        A loopback bind alone does not validate the hostname a browser used to
        reach a local service. The demo deliberately supports only its documented
        literal address, not arbitrary local aliases or public DNS names.
        """
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            self._json(403, {"error": "Use the documented 127.0.0.1 address"})
            return False
        return True

    def _read_body(self) -> object:
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise DemoInputError("Content-Type must be application/json")
        origin = self.headers.get("Origin")
        # Reject cross-origin browser requests, including unsolicited loopback POSTs.
        if origin is not None and origin != f"http://127.0.0.1:{self.server.server_port}":
            raise DemoInputError("Cross-origin requests are not accepted")
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or int(length) > 16384:
            raise DemoInputError("Expected JSON body <= 16 KiB")
        try:
            return json.loads(self.rfile.read(int(length)).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise DemoInputError("Malformed JSON") from None

    def _dispatch_error(self, error: Exception):
        if isinstance(error, DemoNotFound):
            return self._json(404, {"error": "Unknown synthetic resource"})
        if isinstance(error, DemoWriteDisabled):
            return self._json(403, {"error": str(error)})
        if isinstance(error, DemoInputError):
            return self._json(409, {"error": str(error)})
        # No raw exception strings, tracebacks, credentials, or business data.
        return self._json(500, {"error": "Internal demo error"})

    def do_GET(self):
        if not self._require_local_host():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path in STATIC_FILES:
                name, mime = STATIC_FILES[path]
                body = (STATIC / name).read_bytes()
                self._headers(200, mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/health":
                return self._json(200, {"status": "healthy", "mode": "deterministic-offline-demo",
                                        "synthetic": True, "writes_enabled": self.engine.allow_in_memory_writes})
            if path == "/api/demo/orders":
                return self._json(200, {"orders": self.engine.orders(), "synthetic": True})
            if path == "/api/history":
                sessions = self.engine.sessions()
                return self._json(200, {"sessions": sessions, "total": len(sessions), "page": 1,
                                        "limit": 100})
            if path.startswith("/api/history/") and path.endswith("/messages"):
                thread_id = path.split("/")[3]
                return self._json(200, {"thread_id": thread_id,
                                        "messages": self.engine.display_messages(thread_id)})
            if path.startswith("/api/chat/") and path.endswith("/history"):
                thread_id = path.split("/")[3]
                return self._json(200, self.engine.checkpoint_summary(thread_id))

            # Matches the paths consumed by the original 8-tool MCP adapter.
            # A leading /api/ is optional for a conventional base_url layout.
            business_path = path[4:] if path.startswith("/api/") else path
            if business_path == "/suppliers/search":
                term = query.get("name", [""])[0].lower()
                return self._json(200, _business([s for s in SUPPLIERS if term in s["name"].lower()]))
            if business_path == "/parts/page":
                term = query.get("name", [""])[0].lower()
                rows = [p for p in PARTS if term in p["name"].lower()]
                return self._json(200, _business({"records": rows, "total": len(rows), "current": 1,
                                                  "size": len(rows)}))
            if business_path == "/parts/search":
                term = query.get("name", [""])[0].lower()
                return self._json(200, _business([p for p in PARTS if term in p["name"].lower()]))
            if business_path.startswith("/parts/supplier/"):
                supplier_id = int(business_path.rsplit("/", 1)[-1])
                return self._json(200, _business([p for p in PARTS if p["supplierId"] == supplier_id]))
            if business_path == "/inventory/warning":
                warnings = [dict(i, partDetail=next(p for p in PARTS if p["id"] == i["partId"]))
                            for i in INVENTORY if i["quantity"] < i["safetyStock"]]
                return self._json(200, _business(warnings))
            if business_path == "/orders/search-details":
                return self._json(200, _business(self.engine.orders()))
            return self._json(404, {"error": "Unknown demo endpoint"})
        except Exception as error:
            return self._dispatch_error(error)

    def do_POST(self):
        if not self._require_local_host():
            return
        path = urlsplit(self.path).path
        try:
            data = self._read_body()
            if not isinstance(data, dict):
                raise DemoInputError("Body must be a JSON object")
            if path == "/api/chat/stream":
                thread_id, events = self.engine.chat(data.get("message"), data.get("thread_id"))
                return self._send_events(events)
            if path.startswith("/api/chat/") and path.endswith("/resume"):
                thread_id = path.split("/")[3]
                return self._send_events(self.engine.resume(thread_id, data.get("approval_id"), data.get("resume")))
            business_path = path[4:] if path.startswith("/api/") else path
            if business_path == "/orders/create":
                result = self.engine.create_order(data, idempotency_key=self.headers.get("Idempotency-Key"))
                return self._json(200, _business(result))
            return self._json(404, {"error": "Unknown demo endpoint"})
        except Exception as error:
            return self._dispatch_error(error)

    def do_PUT(self):
        if not self._require_local_host():
            return
        path = urlsplit(self.path).path
        try:
            data = self._read_body()
            business_path = path[4:] if path.startswith("/api/") else path
            if business_path.startswith("/orders/update/"):
                order_id = int(business_path.rsplit("/", 1)[-1])
                result = self.engine.update_order(order_id, data)
                return self._json(200, _business(result))
            return self._json(404, {"error": "Unknown demo endpoint"})
        except Exception as error:
            return self._dispatch_error(error)


def main():
    parser = argparse.ArgumentParser(description="Loopback-only, synthetic ProcureFlow demo")
    parser.add_argument("--port", type=int, default=18881)
    parser.add_argument("--allow-in-memory-writes", action="store_true",
                        help="Allow disposable fake orders in RAM; never reaches real ERP")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be in 1024..65535")
    DemoHandler.engine = DemoEngine(allow_in_memory_writes=args.allow_in_memory_writes)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    server.daemon_threads = True
    print(f"OFFLINE_DEMO_READY=http://127.0.0.1:{args.port}", flush=True)
    print(f"SYNTHETIC_WRITES_ENABLED={args.allow_in_memory_writes}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
