import http.server
import socketserver
import threading
from functools import partial


def start_http_handler(directory="ui", port=8000):
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    try:
        httpd = socketserver.TCPServer(("", port), handler, bind_and_activate=False)
        httpd.allow_reuse_address = True
        httpd.server_bind()
        httpd.server_activate()
    except Exception as exc:
        print(f"[HTTP] Failed to start HTTP server on port {port}: {exc}")
        return None

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"Serving HTTP at http://localhost:{port}/")
    return httpd
