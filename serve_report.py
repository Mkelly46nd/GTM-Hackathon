"""
Serve the deduplication report UI and JSON from the project folder.
Run: python serve_report.py
Then open http://localhost:8080/deduplication_report.html (browser may open automatically).
"""
import http.server
import socketserver
import webbrowser
import os

PORT = 8080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(SCRIPT_DIR)

Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    url = f"http://localhost:{PORT}/deduplication_report.html"
    print(f"Serving at {url}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    httpd.serve_forever()
