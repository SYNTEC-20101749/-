import json
from pathlib import Path
from queue import Queue
import ssl
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PyQt5.QtCore import QSettings, QTimer
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from invoice_desktop.main import APP_VERSION, MainWindow
from invoice_desktop.release_updates import (
    LATEST_RELEASE_API, MAX_RESPONSE_BYTES, RELEASES_URL, REQUEST_TIMEOUT_SECONDS,
    ReleaseUpdateCheck, _query_release, fetch_latest_release, newer_release_tag, parse_version,
)


def release_payload(tag="v1.0.15", **extra):
    data = dict(tag_name=tag, draft=False, prerelease=False)
    data.update(extra)
    return json.dumps(data).encode("utf-8")


class ReleaseVersionTests(unittest.TestCase):
    def test_numeric_comparison_and_trailing_zero(self):
        self.assertGreater(parse_version("v1.0.14"), parse_version("1.0.9"))
        self.assertEqual(parse_version("V1.0.14.0"), parse_version("1.0.14"))
        self.assertEqual(newer_release_tag(release_payload("1.0.15"), "1.0.14"), "v1.0.15")
        self.assertEqual(newer_release_tag(release_payload("v1.0.14.1"), "1.0.14"), "v1.0.14.1")
        for tag in ("v1.0.9", "v1.0.14", "v1.0.14.0"):
            with self.subTest(tag=tag):
                self.assertEqual(newer_release_tag(release_payload(tag), "1.0.14"), "")

    def test_drafts_and_prereleases_are_not_offered(self):
        for fields in (dict(draft=True), dict(prerelease=True)):
            self.assertEqual(newer_release_tag(release_payload(**fields), "1.0.14"), "")

    def test_invalid_data_is_not_treated_as_current_version(self):
        for payload in (b"{}", b"[]", b"null", b"not json", b"\xff",
                        release_payload("v1.0.15-beta"), release_payload(None)):
            with self.subTest(payload=payload):
                with self.assertRaises((ValueError, UnicodeError)):
                    newer_release_tag(payload, "1.0.14")


class ReleaseTransportTests(unittest.TestCase):
    def test_python_https_keeps_certificate_checks_and_bounds_response(self):
        with patch("invoice_desktop.release_updates.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.read.return_value = release_payload()
            self.assertEqual(fetch_latest_release("1.0.14"), "v1.0.15")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, LATEST_RELEASE_API)
        self.assertEqual(request.get_header("User-agent"), "SYNTEC-InvoiceManager-UpdateCheck")
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(open_url.call_args.kwargs["timeout"], REQUEST_TIMEOUT_SECONDS)
        context = open_url.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        open_url.return_value.__exit__.assert_called_once()

    def test_oversized_response_is_rejected_and_closed(self):
        with patch("invoice_desktop.release_updates.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "过大"):
                fetch_latest_release("1.0.14")
        open_url.return_value.__exit__.assert_called_once()

    def test_python_https_still_works_when_qt_ssl_is_unavailable(self):
        # 复现Python3.12 + Qt5缺少OpenSSL1.1：Qt TLS不可用不应影响检查。
        with patch("PyQt5.QtNetwork.QSslSocket.supportsSsl", return_value=False), \
             patch("invoice_desktop.release_updates.urlopen") as open_url:
            open_url.return_value.__enter__.return_value.read.return_value = release_payload()
            self.assertEqual(fetch_latest_release("1.0.14"), "v1.0.15")

    def test_background_errors_have_actionable_messages_without_private_details(self):
        certificate_error = ssl.SSLCertVerificationError(1, "private host")
        cases = [
            (TimeoutError("private host"), "超时"),
            (URLError(TimeoutError("private host")), "超时"),
            (URLError(certificate_error), "证书校验"),
            (URLError(ssl.SSLError("private host")), "HTTPS连接"),
            (URLError("private host"), "代理"),
            (HTTPError(LATEST_RELEASE_API, 403, "private host", {"X-RateLimit-Remaining": "0"}, None), "次数"),
            (HTTPError(LATEST_RELEASE_API, 429, "private host", {}, None), "次数"),
            (HTTPError(LATEST_RELEASE_API, 404, "private host", {}, None), "HTTP 404"),
            (ValueError("private host"), "无效"),
            (RuntimeError("private host"), "检查更新失败"),
        ]
        for error, expected in cases:
            with self.subTest(error=error):
                results = Queue()
                with patch("invoice_desktop.release_updates.fetch_latest_release", side_effect=error):
                    _query_release("1.0.14", results, Event())
                kind, message = results.get_nowait()
                self.assertEqual(kind, "failed")
                self.assertIn(expected, message)
                self.assertNotIn("private host", message)

    def test_cancelled_worker_does_not_open_connection_or_publish_late_result(self):
        results, cancelled = Queue(), Event()
        cancelled.set()
        with patch("invoice_desktop.release_updates.fetch_latest_release") as fetch:
            _query_release("1.0.14", results, cancelled)
            fetch.assert_not_called()
        cancelled.clear()

        def cancel_during_request(version):
            cancelled.set()
            return "v1.0.15"

        with patch("invoice_desktop.release_updates.fetch_latest_release", side_effect=cancel_during_request):
            _query_release("1.0.14", results, cancelled)
        self.assertTrue(results.empty())


class ReleaseUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_checker(self):
        thread_patch = patch("invoice_desktop.release_updates.Thread")
        self.addCleanup(thread_patch.stop)
        thread = thread_patch.start()
        checker = ReleaseUpdateCheck("1.0.14")
        self.addCleanup(checker.cancel)
        checked, failed = [], []
        checker.checked.connect(checked.append)
        checker.failed.connect(failed.append)
        return checker, thread, checked, failed

    def test_request_is_async_single_and_finishes_with_new_version(self):
        checker, thread, checked, failed = self.make_checker()
        checker.start()
        checker.start()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertTrue(thread.call_args.kwargs["daemon"])
        self.assertIs(thread.call_args.kwargs["target"], _query_release)
        args = thread.call_args.kwargs["args"]
        self.assertEqual(args, ("1.0.14", checker.results, checker.cancel_event))
        self.assertEqual(checked, [])
        self.assertTrue(checker.timer.isActive())
        with patch("invoice_desktop.release_updates.fetch_latest_release", return_value="v1.0.15"):
            _query_release(*args)
        checker._poll_result()
        self.assertEqual(checked, ["v1.0.15"])
        self.assertEqual(failed, [])
        self.assertFalse(checker.timer.isActive())

    def test_current_version_success(self):
        checker, _, checked, failed = self.make_checker()
        checker.start()
        checker.results.put(("checked", ""))
        checker._poll_result()
        self.assertEqual(checked, [""])
        self.assertEqual(failed, [])

    def test_network_and_json_failure_never_claim_latest(self):
        for error in (URLError("DNS failed"), ValueError("bad json")):
            with self.subTest(error=error):
                checker, _, checked, failed = self.make_checker()
                checker.start()
                with patch("invoice_desktop.release_updates.fetch_latest_release", side_effect=error):
                    _query_release(checker.current_version, checker.results, checker.cancel_event)
                checker._poll_result()
                self.assertEqual(checked, [])
                self.assertEqual(len(failed), 1)
                self.assertFalse(checker.timer.isActive())

    def test_deadline_timeout_ignores_late_result(self):
        checker, _, checked, failed = self.make_checker()
        checker.start()
        checker.deadline = 0
        checker._poll_result()
        checker.results.put(("checked", "v1.0.15"))
        checker._poll_result()
        self.assertTrue(checker.cancel_event.is_set())
        self.assertEqual(checked, [])
        self.assertEqual(len(failed), 1)
        self.assertIn("超时", failed[0])
        self.assertFalse(checker.timer.isActive())

    def test_close_cancels_pending_request_without_emitting(self):
        checker, _, checked, failed = self.make_checker()
        checker.start()
        checker.cancel()
        checker.results.put(("checked", "v1.0.15"))
        checker._poll_result()
        self.assertTrue(checker.cancel_event.is_set())
        self.assertEqual(checked, [])
        self.assertEqual(failed, [])

    def test_cancel_before_scheduled_start_never_opens_connection(self):
        checker, thread, checked, failed = self.make_checker()
        checker.cancel()
        checker.start()
        thread.assert_not_called()
        self.assertEqual(checked, [])
        self.assertEqual(failed, [])


class AboutUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.IniFormat)
        with patch("invoice_desktop.main.QSettings", return_value=settings):
            self.window = MainWindow()
        self.addCleanup(self.window.close)

    def run_about(self, result, inspect):
        def exec_dialog(dialog):
            checker = dialog.findChild(ReleaseUpdateCheck)
            self.assertIsNotNone(checker)
            self.assertEqual(checker.current_version, APP_VERSION)
            label = dialog.findChild(QLabel, "releaseUpdateLabel")
            button = dialog.findChild(QPushButton, "releaseDownloadButton")
            self.assertIn("检查", label.text())
            self.assertTrue(button.isHidden())
            checker.start()
            if result is not None:
                checker.results.put(result)
                checker._poll_result()
            inspect(dialog, label, button)
            dialog.reject()
            self.assertTrue(checker.cancelled)
            return 0

        with patch("invoice_desktop.release_updates.Thread"):
            with patch("invoice_desktop.main.QDialog.exec_", new=exec_dialog):
                self.window.show_about()

    def test_new_version_is_red_and_download_opens_only_fixed_releases_page(self):
        def inspect(dialog, label, button):
            self.assertEqual(label.text(), "有新版本 v1.0.15")
            self.assertIn("#C62828", label.styleSheet())
            self.assertFalse(button.isHidden())
            with patch("invoice_desktop.main.QDesktopServices.openUrl") as open_url:
                button.click()
                open_url.assert_called_once()
                self.assertEqual(open_url.call_args.args[0].toString(), RELEASES_URL)

        self.run_about(("checked", "v1.0.15"), inspect)

    def test_same_version_hides_download(self):
        def inspect(dialog, label, button):
            self.assertIn("最新版本", label.text())
            self.assertTrue(button.isHidden())
        self.run_about(("checked", ""), inspect)

    def test_failure_shows_specific_reason_and_manual_download(self):
        message = "HTTPS证书校验失败，请检查系统时间及网络证书"
        def inspect(dialog, label, button):
            self.assertEqual(label.text(), message)
            self.assertEqual(label.toolTip(), message)
            self.assertFalse(button.isHidden())
        self.run_about(("failed", message), inspect)

    def test_closing_about_with_active_request_aborts_safely(self):
        self.run_about(None, lambda dialog, label, button: self.assertIn("检查", label.text()))

    def test_real_modal_event_loop_processes_scheduled_check_and_response(self):
        results = []

        class ModalDialog(QDialog):
            def exec_(dialog):
                checker = dialog.findChild(ReleaseUpdateCheck)
                watchdog = QTimer(dialog)
                watchdog.setSingleShot(True)
                watchdog.timeout.connect(dialog.reject)
                dialog.finished.connect(watchdog.stop)
                watchdog.start(1000)

                def checked(tag):
                    label = dialog.findChild(QLabel, "releaseUpdateLabel")
                    button = dialog.findChild(QPushButton, "releaseDownloadButton")
                    results.append((tag, label.text(), button.isVisible()))
                    dialog.accept()

                checker.checked.connect(checked)
                return super().exec_()

        with patch("invoice_desktop.release_updates.fetch_latest_release", return_value="v1.0.15") as fetch, \
             patch("invoice_desktop.main.QDialog", ModalDialog):
            self.window.show_about()
            fetch.assert_called_once_with(APP_VERSION)
        self.assertEqual(results, [("v1.0.15", "有新版本 v1.0.15", True)])


if __name__ == "__main__":
    unittest.main()