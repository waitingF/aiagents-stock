"""Notification delivery service used by monitoring and scheduled analysis."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Tuple


class NotificationService:
    """Send email/webhook notifications, with a local fallback queue."""

    def __init__(self) -> None:
        from dotenv import load_dotenv

        load_dotenv()
        self.config = self._load_config()
        self._local_notifications: List[Dict] = []

    def _load_config(self) -> Dict:
        return {
            "email_enabled": os.getenv("EMAIL_ENABLED", "false").lower() == "true",
            "smtp_server": os.getenv("SMTP_SERVER", ""),
            "smtp_port": int(os.getenv("SMTP_PORT", "587") or 587),
            "email_from": os.getenv("EMAIL_FROM", ""),
            "email_password": os.getenv("EMAIL_PASSWORD", ""),
            "email_to": os.getenv("EMAIL_TO", ""),
            "webhook_enabled": os.getenv("WEBHOOK_ENABLED", "false").lower() == "true",
            "webhook_url": os.getenv("WEBHOOK_URL", ""),
            "webhook_type": os.getenv("WEBHOOK_TYPE", "dingtalk").lower(),
            "webhook_keyword": os.getenv("WEBHOOK_KEYWORD", "aiagents notification"),
        }

    def reload(self) -> None:
        self.config = self._load_config()

    def send_notifications(self) -> None:
        from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

        for notification in monitor_db.get_pending_notifications():
            if self.send_notification(notification):
                monitor_db.mark_notification_sent(notification["id"])

    def send_notification(self, notification: Dict) -> bool:
        success = False
        if self.config["webhook_enabled"]:
            success = self._send_webhook_notification(notification) or success
        if self.config["email_enabled"]:
            success = self._send_email_notification(notification) or success
        if not success:
            self._store_local_notification(notification)
            success = True
        return success

    def _send_email_notification(self, notification: Dict) -> bool:
        if not all(
            [
                self.config["smtp_server"],
                self.config["email_from"],
                self.config["email_password"],
                self.config["email_to"],
            ]
        ):
            return False

        subject = f"Stock monitor alert - {notification.get('symbol', '')}"
        body = f"""
        <h2>Stock monitor alert</h2>
        <p><strong>Symbol:</strong> {notification.get('symbol', '')}</p>
        <p><strong>Name:</strong> {notification.get('name', '')}</p>
        <p><strong>Type:</strong> {notification.get('type', '')}</p>
        <p><strong>Message:</strong> {notification.get('message', '')}</p>
        <p><strong>Triggered at:</strong> {notification.get('triggered_at', '')}</p>
        """
        return self._send_custom_email(subject, body, body)

    def _send_custom_email(self, subject: str, html_body: str, text_body: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config["email_from"]
            msg["To"] = self.config["email_to"]
            msg["Subject"] = subject
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            if self.config["smtp_port"] == 465:
                server = smtplib.SMTP_SSL(
                    self.config["smtp_server"], self.config["smtp_port"], timeout=15
                )
            else:
                server = smtplib.SMTP(
                    self.config["smtp_server"], self.config["smtp_port"], timeout=15
                )
                server.starttls()
            with server:
                server.login(self.config["email_from"], self.config["email_password"])
                server.send_message(msg)
            return True
        except Exception as exc:
            print(f"[notification] email failed: {exc}")
            return False

    def _send_webhook_notification(self, notification: Dict) -> bool:
        if not self.config["webhook_url"]:
            return False
        if self.config["webhook_type"] == "feishu":
            return self._send_feishu_webhook(notification)
        return self._send_dingtalk_webhook(notification)

    def _send_dingtalk_webhook(self, notification: Dict) -> bool:
        try:
            import requests

            keyword = self.config.get("webhook_keyword", "")
            title = f"{keyword} - {notification.get('symbol', '')}".strip(" -")
            text = (
                f"### {title}\n\n"
                f"**Name**: {notification.get('name', '')}\n\n"
                f"**Type**: {notification.get('type', '')}\n\n"
                f"**Message**: {notification.get('message', '')}\n\n"
                f"**Triggered at**: {notification.get('triggered_at', '')}"
            )
            response = requests.post(
                self.config["webhook_url"],
                json={"msgtype": "markdown", "markdown": {"title": title, "text": text}},
                timeout=10,
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            return payload.get("errcode", 0) == 0
        except Exception as exc:
            print(f"[notification] dingtalk webhook failed: {exc}")
            return False

    def _send_feishu_webhook(self, notification: Dict) -> bool:
        try:
            import requests

            content = (
                f"{notification.get('symbol', '')} {notification.get('name', '')}\n"
                f"{notification.get('type', '')}\n"
                f"{notification.get('message', '')}\n"
                f"{notification.get('triggered_at', '')}"
            )
            response = requests.post(
                self.config["webhook_url"],
                json={"msg_type": "text", "content": {"text": content}},
                timeout=10,
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            return payload.get("code", 0) == 0
        except Exception as exc:
            print(f"[notification] feishu webhook failed: {exc}")
            return False

    def _store_local_notification(self, notification: Dict) -> None:
        key = (
            f"{notification.get('symbol', '')}_"
            f"{notification.get('type', '')}_"
            f"{notification.get('triggered_at', '')}"
        )
        if key in [item.get("key") for item in self._local_notifications]:
            return
        self._local_notifications.append(
            {
                "key": key,
                "symbol": notification.get("symbol", ""),
                "name": notification.get("name", ""),
                "type": notification.get("type", ""),
                "message": notification.get("message", ""),
                "timestamp": notification.get("triggered_at", ""),
            }
        )

    def get_local_notifications(self) -> List[Dict]:
        return list(self._local_notifications)

    def clear_local_notifications(self) -> None:
        self._local_notifications = []

    def test_email_config(self) -> bool:
        if not self.config["email_enabled"]:
            return False
        try:
            if self.config["smtp_port"] == 465:
                server = smtplib.SMTP_SSL(
                    self.config["smtp_server"], self.config["smtp_port"], timeout=10
                )
            else:
                server = smtplib.SMTP(
                    self.config["smtp_server"], self.config["smtp_port"], timeout=10
                )
                server.starttls()
            with server:
                server.login(self.config["email_from"], self.config["email_password"])
            return True
        except Exception as exc:
            print(f"[notification] email config test failed: {exc}")
            return False

    def send_test_email(self) -> Tuple[bool, str]:
        if not all(
            [
                self.config["smtp_server"],
                self.config["email_from"],
                self.config["email_password"],
                self.config["email_to"],
            ]
        ):
            return False, "邮件配置不完整。"
        success = self._send_custom_email(
            "智策股票 - 邮件测试",
            "<p>邮件通知测试成功。</p>",
            "邮件通知测试成功。",
        )
        return success, "邮件测试已发送。" if success else "邮件测试发送失败。"

    def send_test_webhook(self) -> Tuple[bool, str]:
        success = self._send_webhook_notification(
            {
                "symbol": "TEST",
                "name": "通知回调测试",
                "type": "system",
                "message": "通知回调测试。",
                "triggered_at": "now",
            }
        )
        return success, "通知回调测试已发送。" if success else "通知回调测试发送失败。"

    def send_text(self, title: str, content: str) -> bool:
        return self._send_webhook_notification(
            {
                "symbol": title,
                "name": title,
                "type": "text",
                "message": content,
                "triggered_at": "",
            }
        )

    def send_markdown(self, title: str, content: str) -> bool:
        return self.send_text(title, content)

    def send_test(self) -> Tuple[bool, str]:
        return self.send_test_webhook()

    def get_email_config_status(self) -> Dict:
        return {
            "enabled": self.config["email_enabled"],
            "smtp_server": self.config["smtp_server"],
            "smtp_port": self.config["smtp_port"],
            "email_from": self.config["email_from"],
            "email_to": self.config["email_to"],
            "configured": all(
                [
                    self.config["smtp_server"],
                    self.config["email_from"],
                    self.config["email_password"],
                    self.config["email_to"],
                ]
            ),
        }

    def get_webhook_config_status(self) -> Dict:
        return {
            "enabled": self.config["webhook_enabled"],
            "webhook_type": self.config["webhook_type"],
            "webhook_url": (
                self.config["webhook_url"][:50] + "..."
                if self.config["webhook_url"]
                else ""
            ),
            "configured": bool(self.config["webhook_url"]),
        }

    def send_portfolio_analysis_notification(
        self, analysis_results: dict, sync_result: dict | None = None
    ) -> bool:
        total = analysis_results.get("total", 0)
        succeeded = analysis_results.get("succeeded") or len(
            [item for item in analysis_results.get("results", []) if item.get("result", {}).get("success")]
        )
        failed = analysis_results.get("failed") or max(total - succeeded, 0)
        sync_text = ""
        if sync_result:
            sync_text = (
                f"\n监测同步：新增 {sync_result.get('added', 0)}，"
                f"更新 {sync_result.get('updated', 0)}，失败 {sync_result.get('failed', 0)}"
            )
        message = f"持仓分析完成。总数={total}，成功={succeeded}，失败={failed}。{sync_text}"
        return self.send_text("持仓分析完成", message)


notification_service = NotificationService()
