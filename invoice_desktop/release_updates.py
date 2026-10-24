"""仅在用户打开版本页面时，异步查询GitHub最新正式发布。"""

from __future__ import annotations

import json
from queue import Empty, Queue
import re
import socket
import ssl
from threading import Event, Thread
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


RELEASES_URL = "https://github.com/SYNTEC-20101749/-/releases"
LATEST_RELEASE_API = "https://api.github.com/repos/SYNTEC-20101749/-/releases/latest"
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10
CHECK_TIMEOUT_SECONDS = 12


def parse_version(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"[vV]?(\d+\.\d+\.\d+(?:\.\d+)?)", value.strip())
    if match is None:
        raise ValueError("版本号格式不正确")
    parts = tuple(int(part) for part in match.group(1).split("."))
    return parts + (0,) * (4 - len(parts))


def newer_release_tag(payload: bytes, current_version: str) -> str:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("版本响应格式不正确")
    if data.get("draft") or data.get("prerelease"):
        return ""
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("版本响应缺少版本号")
    return "v" + tag.strip().lstrip("vV") if parse_version(tag) > parse_version(current_version) else ""


def fetch_latest_release(current_version: str) -> str:
    # Qt 5的HTTPS依赖OpenSSL 1.1；Python 3.12提供OpenSSL 3，不能混用。
    # 使用当前Python自己的TLS栈，保留系统证书校验及urllib默认系统代理行为。
    request = Request(LATEST_RELEASE_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "SYNTEC-InvoiceManager-UpdateCheck",
    })
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS,
                 context=ssl.create_default_context()) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("版本响应过大")
    return newer_release_tag(payload, current_version)


def _query_release(current_version: str, results: Queue, cancelled: Event) -> None:
    """后台仅处理Python数据，不访问Qt对象；窗口关闭无需等待网络线程。"""
    if cancelled.is_set():
        return
    try:
        result = ("checked", fetch_latest_release(current_version))
    except HTTPError as exc:
        if exc.code == 429 or (exc.code == 403 and (exc.headers or {}).get("X-RateLimit-Remaining") == "0"):
            message = "GitHub请求次数已达限制，请稍后重试"
        else:
            message = f"GitHub请求失败（HTTP {exc.code}），可打开下载页面查看"
        if exc.fp is not None:
            exc.close()
        result = ("failed", message)
    except (TimeoutError, socket.timeout):
        result = ("failed", "检查超时，请稍后重试")
    except (URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(reason, ssl.SSLCertVerificationError):
            message = "HTTPS证书校验失败，请检查系统时间及网络证书"
        elif isinstance(reason, ssl.SSLError):
            message = "HTTPS连接失败，请检查网络或代理设置"
        elif isinstance(reason, (TimeoutError, socket.timeout)):
            message = "检查超时，请稍后重试"
        else:
            message = "无法连接GitHub，请检查网络或代理设置"
        result = ("failed", message)
    except (ValueError, UnicodeError, OverflowError):
        result = ("failed", "版本信息无效或响应过大，请稍后重试")
    except Exception:
        result = ("failed", "检查更新失败，可打开下载页面查看")
    if not cancelled.is_set():
        results.put(result)


class ReleaseUpdateCheck(QObject):
    checked = pyqtSignal(str)  # 新版本标签；空字符串表示当前无需更新。
    failed = pyqtSignal(str)

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll_result)
        self.results = Queue()
        self.cancel_event = Event()
        self.deadline = 0.0
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        if self.started or self.cancelled:
            return
        self.started = True
        self.deadline = monotonic() + CHECK_TIMEOUT_SECONDS
        # 不捕获self或任何Qt对象；即使网络仍在等待，关闭对话框也不会访问已销毁控件。
        worker = Thread(target=_query_release,
                        args=(self.current_version, self.results, self.cancel_event),
                        name="InvoiceReleaseUpdate", daemon=True)
        worker.start()
        self.timer.start()

    def _poll_result(self) -> None:
        if self.cancelled:
            return
        try:
            kind, value = self.results.get_nowait()
        except Empty:
            if monotonic() >= self.deadline:
                self._timeout()
            return
        self.timer.stop()
        if kind == "checked":
            self.checked.emit(value)
        else:
            self.failed.emit(value)

    def _timeout(self) -> None:
        self.cancel()
        self.failed.emit("检查超时，请稍后重试")

    def cancel(self, *args) -> None:
        self.cancelled = True
        self.cancel_event.set()
        self.timer.stop()