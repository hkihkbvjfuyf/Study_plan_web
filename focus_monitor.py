"""专注监控 — 后台运行，检测摸鱼行为并记录到 focus_state.json"""
import json
import os
import time
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "focus_state.json")
CONFIG_FILE = os.path.join(BASE_DIR, "focus_config.json")

# ====== 规则配置（从 focus_config.json 加载） ======
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return (
                cfg.get("distraction_keywords", []),
                cfg.get("whitelist_keywords", [])
            )
        except (json.JSONDecodeError, IOError):
            pass
    return ([], [])

DISTRACTION_KEYWORDS, WHITELIST_KEYWORDS = load_config()

CHECK_INTERVAL = 3  # 检测间隔（秒）
IDLE_THRESHOLD = 120  # 连续无变化超过此时间视为离开（秒）
CONFIG_RELOAD_INTERVAL = 30  # 配置重载间隔（秒）
last_config_reload = time.time()

# ====== 核心函数 ======

def get_active_window_title():
    """获取当前活动窗口标题"""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""


def clean_title(title):
    """清理窗口标题：去掉浏览器折叠标签数、后缀等，只保留活动页面标题"""
    if not title:
        return title
    import re
    # 去掉 " 和另外 X 个页面" 及之后的部分
    title = re.sub(r'\s*和另外\s*\d+\s*个页面.*$', '', title, flags=re.IGNORECASE)
    # 去掉 " - 个人 - Microsoft Edge" 等浏览器后缀
    title = re.sub(r'\s*[-–—]\s*个人\s*[-–—]\s*Microsoft\s*Edge\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*[-–—]\s*Google\s*Chrome\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*[-–—]\s*Mozilla\s*Firefox\s*$', '', title, flags=re.IGNORECASE)
    # 去掉末尾空白
    title = title.strip()
    return title


def classify_window(title):
    """
    判断窗口类别。
    返回: ('distraction', keyword) | ('study', None) | ('neutral', None)
    """
    if not title or title.strip() == "":
        return ('idle', None)

    title_lower = title.lower()

    # 先检查白名单
    for kw in WHITELIST_KEYWORDS:
        if kw.lower() in title_lower:
            return ('study', None)

    # 检查摸鱼关键词
    for kw in DISTRACTION_KEYWORDS:
        if kw.lower() in title_lower:
            return ('distraction', kw)

    return ('neutral', None)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"sessions": {}, "today_summary": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def main():
    global DISTRACTION_KEYWORDS, WHITELIST_KEYWORDS, last_config_reload

    print("专注监控已启动 — 按 Ctrl+C 停止")
    print(f"检测间隔: {CHECK_INTERVAL}s | 离开阈值: {IDLE_THRESHOLD}s")
    print(f"摸鱼关键词: {len(DISTRACTION_KEYWORDS)} 个 | 白名单: {len(WHITELIST_KEYWORDS)} 个")
    print("-" * 40)

    state = load_state()
    current_session = None  # 当前摸鱼/学习 session
    last_title = ""
    last_change_time = time.time()

    try:
        while True:
            title = clean_title(get_active_window_title())
            now = time.time()

            # 定期重载配置
            if now - last_config_reload > CONFIG_RELOAD_INTERVAL:
                DISTRACTION_KEYWORDS, WHITELIST_KEYWORDS = load_config()
                last_config_reload = now

            category, matched_kw = classify_window(title)
            today = today_key()

            # 检测窗口是否变化
            title_changed = (title != last_title)
            if title_changed:
                last_title = title
                last_change_time = now

            # 判断是否空闲
            idle_duration = now - last_change_time
            is_idle = (idle_duration > IDLE_THRESHOLD)

            # 结束当前 session（如果类别变化或空闲超时）
            if current_session and (title_changed or is_idle):
                session_cat = current_session["category"]
                duration = round(now - current_session["start"], 1)
                if duration >= 5:  # 只记录 >=5 秒的 session
                    if today not in state["sessions"]:
                        state["sessions"][today] = []
                    state["sessions"][today].append({
                        "start": datetime.fromtimestamp(current_session["start"]).strftime("%H:%M:%S"),
                        "end": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
                        "duration_sec": duration,
                        "category": session_cat,
                        "title": current_session["title"][:120],
                        "matched": current_session.get("matched", "")
                    })

                    # 更新今日摘要
                    if today not in state["today_summary"]:
                        state["today_summary"][today] = {"distraction_sec": 0, "study_sec": 0, "incidents": 0}
                    summary = state["today_summary"][today]
                    if session_cat == "distraction":
                        summary["distraction_sec"] += duration
                        summary["incidents"] += 1
                    elif session_cat == "study":
                        summary["study_sec"] += duration

                    save_state(state)

                    if session_cat == "distraction":
                        min_str = f"{duration/60:.1f}min"
                        print(f"[{datetime.now().strftime('%H:%M')}] 摸鱼检测: {current_session['title'][:50]} ({min_str})")

                current_session = None

            # 开始新 session
            if not current_session and not is_idle and category in ("distraction", "study"):
                current_session = {
                    "start": now,
                    "category": category,
                    "title": title,
                    "matched": matched_kw
                }

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n专注监控已停止")


if __name__ == "__main__":
    main()
