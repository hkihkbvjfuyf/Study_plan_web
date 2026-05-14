# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

流萤研习室 — 考研备考计划工具。单页 HTML 前端 + Python HTTP 后端 + JSON 文件持久化，配合 Windows 专注监控脚本。

## 启动命令

```bash
python server.py          # 启动服务器 → http://127.0.0.1:8765/
python focus_monitor.py   # 启动专注监控（可选，需 pywin32）
```

纯本地使用：直接用浏览器打开 `五月每日计划.html`（专注监控不可用）。

## 架构

- **`五月每日计划.html`** — 主应用，单文件包含全部 CSS/JS。功能：每日任务打卡、番茄钟计时、学习热力图、周报、光萤之树、成就系统、日记系统、每日总结、专注仪表板。无外部 JS 依赖（仅 Google Fonts）。
- **`pomodoro.html`** — 番茄钟全屏计时页面，从主页面通过 `window.open` 打开，通过 `localStorage` 通信。
- **`server.py`** — Python HTTP 服务端 (port 8765)。路由：`/` → 主 HTML，`/api/state` GET/POST → 读写打卡/日记/总结数据，`/api/focus` GET → 专注数据，`/api/focus_config` GET/POST → 读写黑白名单配置。GET `/api/state` 会自动合并专注数据（`_focus_sessions`、`_focus_summary`）。
- **`focus_monitor.py`** — 后台脚本，每 3 秒检测活动窗口标题，通过 pywin32 或 ctypes fallback 获取。按黑白名单分类窗口为 distraction/study/neutral/idle，记录 ≥5 秒的 session 到 `focus_state.json`。每 30 秒热重载配置。

## 数据文件

| 文件 | 内容 |
|------|------|
| `checklist_state.json` | 打卡状态、番茄钟记录、日记数据、每日总结 |
| `focus_state.json` | 专注监控 sessions + 每日摘要 |
| `focus_config.json` | 摸鱼关键词黑名单 + 学习关键词白名单 |

## 关键时间规则

**凌晨 4 点为日分界**：0:00–3:59 的番茄钟记录和日记归属于前一天。前端 JS 中所有日期计算都遵循此规则。

## 前端通信模式

- 主页与番茄钟页面通过 `localStorage` 传递任务信息和计时状态（key: `pomodoroTask`、`pomodoroSync` 等）
- 主页周期性轮询 `/api/state` 刷新数据
- 专注仪表板数据从 `/api/state` 响应的 `_focus_sessions` 字段获取

## 注意事项

- `focus_monitor.py` 依赖 pywin32（`win32gui`），有 ctypes 回退方案
- 服务器绑定 `127.0.0.1`，仅本地访问
- `checklist_state.json` 和 `focus_state.json` 在 `.gitignore` 中，不提交
