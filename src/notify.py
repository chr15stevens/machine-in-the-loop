"""
OS-level notification, so the page does not have to be open.

No dependencies: every platform already ships something that can raise a
notification, so this shells out rather than pulling in a library.

Click-to-open is not uniformly available, and this module does not pretend
otherwise — `capability()` reports what this machine can actually do:

  Windows   toast with protocol activation; clicking opens the URL.
  macOS     terminal-notifier if installed, which supports clicking.
            Otherwise osascript, which shows the notification but ignores
            clicks — there is no way to attach a URL to an osascript banner.
  Linux     notify-send. Clicking works only if the desktop's notification
            daemon supports actions; where it does not, the button is absent
            and the notification still shows.

Everything is fire-and-forget on a daemon thread. A notification that fails
must never disturb the request that triggered it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from xml.sax.saxutils import escape

from src.config import APP_URL

# Set MITL_NOTIFY=0 to silence OS notifications.
ENABLED = os.environ.get("MITL_NOTIFY", "1").strip().lower() not in {"0", "false", "no"}

TITLE = "machine in the loop"
_TIMEOUT = 20

# Concatenated rather than interpolated: the values arrive as environment
# variables, so nothing from a request text is ever parsed as PowerShell.
_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
$xml = '<toast activationType="protocol" launch="' + $env:MITL_TOAST_URL + '">' +
       '<visual><binding template="ToastGeneric">' +
       '<text>' + $env:MITL_TOAST_TITLE + '</text>' +
       '<text>' + $env:MITL_TOAST_BODY + '</text>' +
       '</binding></visual></toast>'
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def capability() -> str:
    """One line describing what notifications can do here. For the banner."""
    if not ENABLED:
        return "off — MITL_NOTIFY=0"
    if sys.platform == "win32":
        return "on — click opens the page"
    if sys.platform == "darwin":
        if shutil.which("terminal-notifier"):
            return "on — click opens the page"
        return "on — click does nothing (brew install terminal-notifier to fix)"
    if shutil.which("notify-send"):
        return "on — click opens the page if your desktop supports actions"
    return "off — notify-send not found"


def notify(body: str, url: str = APP_URL, title: str = TITLE) -> None:
    """Raise a notification. Returns immediately; never raises."""
    if not ENABLED:
        return
    threading.Thread(
        target=_dispatch, args=(title, body, url), daemon=True
    ).start()


def _dispatch(title: str, body: str, url: str) -> None:
    try:
        if sys.platform == "win32":
            _windows(title, body, url)
        elif sys.platform == "darwin":
            _macos(title, body, url)
        else:
            _linux(title, body, url)
    except Exception:
        # A missed notification is a nuisance; a raised one in a background
        # thread is noise in the log for no benefit. The UI remains the
        # source of truth either way.
        pass


def _windows(title: str, body: str, url: str) -> None:
    env = {
        **os.environ,
        "MITL_TOAST_TITLE": escape(title),
        "MITL_TOAST_BODY": escape(body),
        "MITL_TOAST_URL": escape(url, {'"': "&quot;"}),
    }
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "-"],
        input=_WINDOWS_SCRIPT,
        env=env,
        text=True,
        capture_output=True,
        timeout=_TIMEOUT,
        # Without this a console window flashes on every notification.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _macos(title: str, body: str, url: str) -> None:
    notifier = shutil.which("terminal-notifier")
    if notifier:
        subprocess.run(
            [notifier, "-title", title, "-message", body, "-open", url],
            capture_output=True,
            timeout=_TIMEOUT,
        )
        return

    # osascript has no way to attach a click target, so this shows the text
    # and nothing more.
    script = (
        f"display notification {_applescript_str(body)} "
        f"with title {_applescript_str(title)}"
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=_TIMEOUT)


def _applescript_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _linux(title: str, body: str, url: str) -> None:
    if not shutil.which("notify-send"):
        return

    # -A adds a button and blocks until the user acts, printing the action id.
    # Desktops without action support ignore it and return immediately, which
    # is why this is not treated as an error.
    result = subprocess.run(
        ["notify-send", "--app-name", TITLE, "-A", "open=Open", "--", title, body],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if result.stdout.strip() == "open" and shutil.which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
