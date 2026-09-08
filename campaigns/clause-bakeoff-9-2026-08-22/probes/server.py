import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = sys.argv[1]
captured = threading.Event()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _hello(self):
        self.send_response(200); self.send_header("Content-Length","0"); self.end_headers()
    def do_HEAD(self): self._hello()
    def do_GET(self): self._hello()
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if "/v1/messages" in self.path and not captured.is_set():
            with open(OUT, "wb") as f:
                f.write(json.dumps({
                    "path": self.path,
                    "headers": {k: v for k, v in self.headers.items()},
                    "body": json.loads(body.decode("utf-8", "replace")),
                }, indent=2).encode())
            captured.set()
        payload = json.dumps({"type":"error","error":{"type":"authentication_error","message":"synthetic capture stop"}}).encode()
        self.send_response(401)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

srv = HTTPServer(("127.0.0.1", 0), H)
print(srv.server_port, flush=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
captured.wait(timeout=180)
srv.shutdown()
