"""Isolated localhost preview. No WebChannel and no host bridge."""

from urllib.parse import urlsplit
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QMainWindow, QToolBar, QLabel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


def local_origin(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise PermissionError("Preview is restricted to the active localhost development origin")
    return (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))


class OriginInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, origin, parent=None):
        super().__init__(parent)
        self.origin = origin

    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() in {"data", "blob", "about"}:
            return
        try:
            allowed = local_origin(url.toString()) == self.origin
        except (PermissionError, ValueError):
            allowed = False
        info.block(not allowed)


class PreviewPage(QWebEnginePage):
    def __init__(self, profile, origin, parent):
        super().__init__(profile, parent)
        self.origin = origin

    def acceptNavigationRequest(self, url, kind, main_frame):
        if url.toString() == "about:blank":
            return True
        try:
            return local_origin(url.toString()) == self.origin
        except (PermissionError, ValueError):
            return False

    def createWindow(self, window_type):
        return None


class PreviewWindow(QMainWindow):
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OLIVE — Local preview")
        self.resize(1050, 750)
        self.origin = local_origin(url)
        self.profile = QWebEngineProfile()
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.interceptor = OriginInterceptor(self.origin, self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        self.view = QWebEngineView()
        self.page = PreviewPage(self.profile, self.origin, self.view)
        self.page.permissionRequested.connect(lambda permission: permission.deny())
        settings = self.page.settings()
        for attribute in (
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
        ):
            settings.setAttribute(attribute, False)
        self.page.destroyed.connect(self.profile.deleteLater)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        toolbar = QToolBar("Preview")
        self.addToolBar(toolbar)
        toolbar.addAction("Reload", self.view.reload)
        toolbar.addAction("Stop", self.view.stop)
        toolbar.addWidget(QLabel(url))
        self.view.loadFinished.connect(
            lambda ok: self.statusBar().showMessage(
                "Preview ready" if ok else "Preview unavailable or navigation blocked"
            )
        )
        self.view.load(QUrl(url))

    def closeEvent(self, event):
        self.view.stop()
        event.accept()

    def dispose(self):
        self.view.stop()
        self.page.deleteLater()
        self.view.deleteLater()
