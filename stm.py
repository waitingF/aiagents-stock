#!/usr/bin/env python3
"""Streamlit process manager for server deployments."""

from __future__ import annotations

import os
import signal
import subprocess
import time

import psutil
from src.aiagents_stock.core.paths import log_path


APP_NAME = "app.py"
APP_PATH = "/www/wwwroot/aiagents-stock"
VENV_PATH = "/www/wwwroot/aiagents-stock/venv"
PORT = 8501
STREAMLIT_BIN = os.path.join(VENV_PATH, "bin", "streamlit")
LOG_PATH = str(log_path("app.log"))


def is_run() -> int | None:
    """Return the Streamlit process pid if the app is running."""
    for process in psutil.process_iter(["cmdline"]):
        cmdline = process.info.get("cmdline") or []
        cmdline_text = " ".join(cmdline)
        if "streamlit" in cmdline_text and "run" in cmdline:
            return process.pid
    return None


def start() -> None:
    """Start the Streamlit app."""
    if is_run():
        print("⚠️  已在运行")
        return

    os.chdir(APP_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [
                STREAMLIT_BIN,
                "run",
                APP_NAME,
                "--server.port",
                str(PORT),
                "--server.address",
                "0.0.0.0",
                "--server.headless",
                "true",
            ],
            stdout=log_file,
            stderr=log_file,
            preexec_fn=os.setsid,
        )

    time.sleep(3)
    print("✅ 启动成功 | http://服务器IP:8501")


def stop() -> None:
    """Stop the Streamlit app."""
    pid = is_run()
    if not pid:
        print("⚠️  未运行")
        return

    os.kill(pid, signal.SIGTERM)
    time.sleep(2)
    if is_run():
        os.kill(pid, signal.SIGKILL)
    print("✅ 已停止")


def show_status() -> None:
    """Print current running status."""
    print("✅ 运行中" if is_run() else "❌ 未运行")


def show_logs() -> None:
    """Show the latest deployment log lines."""
    os.system("tail -n 50 " + LOG_PATH)


def main() -> None:
    """Interactive command menu."""
    menu = "1) 启动  2) 停止  3) 重启  4) 状态  5) 日志  0) 退出"
    while True:
        print(menu)
        choice = input("选 > ").strip()
        if choice == "1":
            start()
        elif choice == "2":
            stop()
        elif choice == "3":
            stop()
            time.sleep(2)
            start()
        elif choice == "4":
            show_status()
        elif choice == "5":
            show_logs()
        elif choice == "0":
            break
        else:
            print("无效")
        input("\n回车继续 …")


if __name__ == "__main__":
    main()
