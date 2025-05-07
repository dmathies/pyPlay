import http.server
import socketserver
import threading
from functools import partial


def start_http_handler(directory="ui", port=8000):
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    httpd = socketserver.TCPServer(("", port), handler)

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"Serving HTTP at http://localhost:{port}/")

