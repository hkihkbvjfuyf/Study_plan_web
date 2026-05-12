"""考研打卡服务器 — 数据持久化到 checklist_state.json"""
import json
import os
import http.server
import socketserver
from urllib.parse import urlparse, unquote, quote

PORT = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "checklist_state.json")
FOCUS_STATE_FILE = os.path.join(BASE_DIR, "focus_state.json")
FOCUS_CONFIG_FILE = os.path.join(BASE_DIR, "focus_config.json")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/state":
            self._serve_json_file(STATE_FILE, merge_focus=True)
        elif path == "/api/focus":
            self._serve_json_file(FOCUS_STATE_FILE)
        elif path == "/api/focus_config":
            self._serve_json_file(FOCUS_CONFIG_FILE)
        elif path == "/" or path == "/index.html":
            self._serve_file("/五月每日计划.html")
        else:
            self._serve_file(path)

    def _serve_json_file(self, filepath, merge_focus=False):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        data = {}
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        if merge_focus:
            # 合并专注监控数据
            if os.path.exists(FOCUS_STATE_FILE):
                with open(FOCUS_STATE_FILE, "r", encoding="utf-8") as f:
                    focus_data = json.load(f)
                data["_focus_sessions"] = focus_data.get("sessions", {})
                data["_focus_summary"] = focus_data.get("today_summary", {})
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _serve_file(self, path):
        filepath = os.path.normpath(os.path.join(BASE_DIR, path.lstrip("/")))
        if not filepath.startswith(BASE_DIR):
            self.send_error(403)
            return
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        ext = os.path.splitext(filepath)[1].lower()
        content_type = MIME.get(ext, "application/octet-stream")
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(data))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", quote(location, safe='/:?=&'))
        self.end_headers()

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/state":
            self._save_json(STATE_FILE)
        elif path == "/api/focus_config":
            self._save_json(FOCUS_CONFIG_FILE)
        else:
            self.send_response(404)
            self.end_headers()

    def _save_json(self, filepath):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print(f"打卡服务器已启动 → http://127.0.0.1:{PORT}/")
    print("按 Ctrl+C 关闭服务器")
    print()

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已关闭")
