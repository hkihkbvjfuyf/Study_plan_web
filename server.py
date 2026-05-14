"""考研打卡服务器 — 数据持久化到 checklist_state.json"""
import json
import os
import re
import subprocess
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
        elif path == "/api/chat":
            self._handle_chat()
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

    def _handle_chat(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                body = raw.decode("gbk")
            except UnicodeDecodeError:
                self._send_json({"reply": "编码错误，请使用 UTF-8"})
                return
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"reply": "消息格式错误"})
            return
        messages = data.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        if not user_msg.strip():
            self._send_json({"reply": "请输入内容"})
            return

        prompt = self._build_chat_prompt(user_msg)
        try:
            claude_exe = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")
            # 将 prompt 写入临时文件，通过 stdin 重定向传入
            import tempfile
            tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
            tmpf.write(prompt)
            tmpf.close()
            try:
                with open(tmpf.name, "r", encoding="utf-8") as f:
                    result = subprocess.run(
                        [claude_exe, "-p"],
                        stdin=f, capture_output=True, timeout=180,
                        cwd=BASE_DIR,
                        env={**os.environ, "NO_COLOR": "1"}
                    )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            finally:
                try:
                    os.unlink(tmpf.name)
                except OSError:
                    pass
            stdout = stdout.strip()
            stderr = stderr.strip()
            if stdout:
                reply = stdout
            elif stderr:
                reply = "[claude stderr]\n" + stderr[:800]
            else:
                reply = f"（Claude 未返回内容，请重试。rc={result.returncode}）"
        except subprocess.TimeoutExpired:
            reply = "处理超时（3分钟），请简化问题后重试。"
        except FileNotFoundError:
            reply = "未找到 claude 命令，请确认 Claude Code CLI 已安装。"
        except Exception as e:
            reply = f"调用失败: {e}"

        self._send_json({"reply": reply})

    def _build_chat_prompt(self, user_msg):
        parts = []
        # 加载流萤聊天风格
        style = self._load_firefly_style()
        if style:
            parts.append(style)
        else:
            parts.append("你是流萤研习室的 AI 学习助手。请用中文回复，简洁直接。")
        parts.append("")
        parts.append("## 当前计划")
        parts.append(self._read_plan_summary())
        parts.append("")
        parts.append("## 当前进度")
        parts.append(self._read_progress_summary())
        parts.append("")
        parts.append("## 规则")
        parts.append("- 修改计划时直接编辑 D:\\Study_plan\\五月每日计划.html 中的 weeks 数组")
        parts.append("- 只修改未来日期的任务（今天及之后），过去日期的任务不动")
        parts.append("- 保持周边界（周一-周日，每7天一周）")
        parts.append("- 任务格式：[\"category\", \"subtag\", \"具体描述\"]")
        parts.append("- category: math/eng/pro/review，subtag: 数/英/专/复盘")
        parts.append("- 用户偏好：数学用方浩讲义+做题本，英语用扇贝单词(复习300+新学100)，专业课用求臻机械考研")
        parts.append("")
        parts.append("## 用户消息")
        parts.append(user_msg)

        return "\n".join(parts)

    def _load_firefly_style(self):
        """加载流萤聊天风格"""
        style_path = os.path.join(BASE_DIR, "study-plan-2.0.0", "firefly-chat.md")
        if not os.path.exists(style_path):
            return ""
        try:
            with open(style_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 去掉 markdown frontmatter 之外的部分，只保留核心风格描述
            # 去掉标题行和代码块标记，保留正文
            lines = content.split("\n")
            result = []
            in_style = False
            for line in lines:
                if line.startswith("# "):
                    in_style = True
                    continue
                if in_style:
                    # 跳过代码块和空行标记
                    if line.strip().startswith("```") or line.strip().startswith("---"):
                        continue
                    result.append(line)
            style_text = "\n".join(result).strip()
            return style_text if style_text else ""
        except Exception:
            return ""

    def _read_plan_summary(self):
        """读取 weeks 数组的摘要（标题+天数+任务数），用正则提取，避免 JS/JSON 差异"""
        html_path = os.path.join(BASE_DIR, "五月每日计划.html")
        if not os.path.exists(html_path):
            return "（未找到计划文件）"
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            today = __import__("datetime").date.today().strftime("%m月%d日")
            lines = []
            # 提取每周围标题
            week_blocks = re.findall(r'title:\s*"([^"]+)"\s*,\s*subtitle:\s*"([^"]+)"', content)
            # 提取每天信息
            day_blocks = re.findall(
                r'date:\s*"([^"]+)"\s*,\s*label:\s*"([^"]+)"\s*,\s*tag:\s*"([^"]*)"\s*,\s*tagText:\s*"([^"]*)"\s*,\s*tasks:\s*\[([^\]]+)\]',
                content
            )
            for i, (title, subtitle) in enumerate(week_blocks):
                lines.append(f"第{i+1}周: {title} — {subtitle}")
            if day_blocks:
                for date, label, tag, tagText, tasks_raw in day_blocks:
                    marker = " ← 今天" if date == today else ""
                    task_count = len(re.findall(r'\["([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"\]', tasks_raw))
                    lines.append(f"  {date} {label} ({task_count}任务){marker}")
            return "\n".join(lines) if lines else "（未能解析计划数据）"
        except Exception as e:
            return f"（读取计划出错: {e}）"

    def _read_progress_summary(self):
        """读取完成数据摘要"""
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return "（暂无打卡数据）"

        # 统计完成任务
        completed = {k: v for k, v in state.items() if v is True and "_" in k and k.count("_") == 2}
        total_in_plan = 0
        html_path = os.path.join(BASE_DIR, "五月每日计划.html")
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                match = re.search(r"const weeks = (\[[\s\S]*?\]);", f.read())
            if match:
                weeks = json.loads(match.group(1))
                for week in weeks:
                    for day in week.get("days", []):
                        total_in_plan += len(day["tasks"])
        except Exception:
            total_in_plan = "?"

        # 最近日记
        diaries = []
        for k, v in state.items():
            if k.startswith("diary_") and v and isinstance(v, dict):
                diaries.append((k, v))
        diaries.sort(reverse=True)

        lines = [f"已完成: {len(completed)}/{total_in_plan} 个任务"]
        today_key = __import__("datetime").date.today().strftime("%Y-%m-%d")
        summary_key = f"summary_{today_key}"
        if summary_key in state and state[summary_key] and isinstance(state[summary_key], dict):
            s = state[summary_key]
            lines.append(f"今日总结: 评分{s.get('score','?')}/100 — {s.get('comment','')[:100]}")

        if diaries:
            latest = diaries[0]
            d = latest[1]
            lines.append(f"最近日记({latest[0]}): 状态{d.get('mood','?')} 专注{d.get('focus','?')} 困难{d.get('difficulty','?')}")

        return "\n".join(lines)

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

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
