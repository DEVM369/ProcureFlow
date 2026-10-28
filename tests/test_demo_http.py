"""Loopback HTTP contract tests against the included offline server."""

import json
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from demo.engine import DemoEngine
from demo.server import DemoHandler


class HTTPContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class IsolatedHandler(DemoHandler):
            engine = DemoEngine()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), IsolatedHandler)
        cls.httpd.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.worker = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.worker.join(timeout=2)

    def _get(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return json.load(response)

    def _post(self, path, body, *, origin=None, mime="application/json"):
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": mime}
        if origin:
            headers["Origin"] = origin
        req = Request(self.base + path, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=3) as response:
            raw = response.read().decode("utf-8")
            return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]

    def test_health_and_static_browser(self):
        health = self._get("/health")
        self.assertEqual(health["status"], "healthy")
        self.assertFalse(health["writes_enabled"])
        with urlopen(self.base + "/app.js", timeout=3) as response:
            js = response.read().decode("utf-8")
            self.assertIn("receiveEvent", js)
            self.assertIn("application/javascript", response.headers["Content-Type"])

    def test_full_reject_path_over_sse(self):
        events = self._post("/api/chat/stream", {"message": "创建订单"})
        initial = next(e for e in events if e["type"] == "interrupt")
        thread = initial["thread_id"]
        second = self._post(f"/api/chat/{thread}/resume", {
            "approval_id": initial["approval_id"],
            "resume": {"supplement": "物料101 数量50 价格42"},
        })
        approval = next(e for e in second if e["type"] == "interrupt")
        self.assertNotEqual(initial["approval_id"], approval["approval_id"])
        try:
            self._post(f"/api/chat/{thread}/resume", {
                "approval_id": approval["approval_id"],
                "resume": {"decisions": [{"type": "approve"}]},
            })
        except HTTPError as error:
            self.assertEqual(error.code, 403)
            error.close()
        else:
            self.fail("Default write protection must deny approval")
        rejected = self._post(f"/api/chat/{thread}/resume", {
            "approval_id": approval["approval_id"],
            "resume": {"decisions": [{"type": "reject"}]},
        })
        self.assertIn("拒绝", rejected[0]["content"])
        self.assertEqual(self._get("/api/demo/orders")["orders"], [])
        history = self._get(f"/api/chat/{thread}/history")
        self.assertEqual(history["thread_id"], thread)
        self.assertTrue(all("content" not in m for m in history["states"][0]["values"]["messages"]))

    def test_mock_erp_read_shapes(self):
        response = self._get("/api/inventory/warning")
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"][0]["partId"], 101)
        self.assertEqual(self._get("/api/suppliers/search")["code"], 200)
        self.assertEqual(self._get("/api/parts/page")["data"]["total"], 2)

    def test_rebinding_hostname_rejected_even_on_loopback(self):
        # DNS rebinding can present a public Host name while connecting to
        # 127.0.0.1. Both reads and mutations must refuse that request.
        headers = {"Host": "untrusted.example"}
        for method, path, data in (
            ("GET", "/health", None),
            ("POST", "/api/chat/stream", b'{"message":"hello"}'),
            ("PUT", "/api/orders/update/1", b'{"remark":"bad"}'),
        ):
            with self.subTest(method=method):
                request = Request(self.base + path, data=data,
                                  headers=dict(headers, **({"Content-Type": "application/json"}
                                                         if data is not None else {})),
                                  method=method)
                with self.assertRaises(HTTPError) as cm:
                    urlopen(request, timeout=3)
                self.assertEqual(cm.exception.code, 403)
                cm.exception.close()

    def test_cross_origin_and_wrong_content_type_are_denied(self):
        attempts = [
            {"origin": "https://untrusted.example"},
            {"mime": "text/plain"},
        ]
        for headers in attempts:
            with self.subTest(headers=headers):
                with self.assertRaises(HTTPError) as cm:
                    self._post("/api/chat/stream", {"message": "hi"}, **headers)
                self.assertEqual(cm.exception.code, 409)
                cm.exception.close()


if __name__ == "__main__":
    unittest.main()
