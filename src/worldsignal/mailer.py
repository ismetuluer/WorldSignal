"""Open an e-mail draft with an output (meeting list, notes, …). Nothing is ever sent by World Signal:
the user's mail program opens with the draft and the user presses Send.

1. Classic Outlook (registered as ``Outlook.Application``): a draft with the formatted (HTML) output,
   made through Outlook's automation interface from a short PowerShell script.
2. Otherwise the default mail program through a ``mailto:`` link, with the plain-text output. A mailto
   link has a length limit, so a long text is cut; the caller has put the formatted output on the
   clipboard, and the draft says so.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)

MAILTO_BODY_LIMIT = 1800  # characters; longer mailto links fail in some mail programs
OUTLOOK_TIMEOUT = 90  # a cold Outlook start can take a while

_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$enc = New-Object System.Text.UTF8Encoding $false
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.Subject = [IO.File]::ReadAllText($args[0], $enc)
$mail.HTMLBody = [IO.File]::ReadAllText($args[1], $enc)
$mail.Display($false)
"""


class MailError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def outlook_installed() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"))
        return True
    except OSError:
        return False


def outlook_draft(subject: str, html: str) -> bool:
    """True when Outlook showed the draft."""
    with tempfile.TemporaryDirectory(prefix="ws-mail-") as tmp:
        folder = Path(tmp)
        (folder / "subject.txt").write_text(subject, encoding="utf-8")
        (folder / "body.html").write_text(f"<html><body>{html}</body></html>", encoding="utf-8")
        script = folder / "draft.ps1"
        script.write_text(_PS_SCRIPT, encoding="utf-8-sig")
        try:
            done = subprocess.run(  # noqa: S603 - fixed script, our own temporary files
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 str(folder / "subject.txt"), str(folder / "body.html")],
                capture_output=True, text=True, timeout=OUTLOOK_TIMEOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("Outlook draft failed: %s", exc)
            return False
    if done.returncode != 0:
        log.warning("Outlook draft failed (%s): %s", done.returncode, done.stderr.strip()[:500])
        return False
    return True


def mailto_link(subject: str, text: str, cut_note: str) -> tuple[str, bool]:
    body, cut = text, False
    if len(body) > MAILTO_BODY_LIMIT:
        body, cut = body[:MAILTO_BODY_LIMIT].rsplit("\n", 1)[0] + f"\n\n{cut_note}", True
    return f"mailto:?subject={quote(subject)}&body={quote(body)}", cut


def default_mail_draft(subject: str, text: str, cut_note: str) -> bool:
    """Opens the default mail program. Returns whether the text had to be cut."""
    link, cut = mailto_link(subject, text, cut_note)
    try:
        os.startfile(link)  # type: ignore[attr-defined]  # noqa: S606 - a mailto link only
    except OSError as exc:
        log.warning("No mail program for mailto: %s", exc)
        raise MailError("no_mail_program") from exc
    return cut


def open_draft(subject: str, html: str, text: str, cut_note: str) -> dict[str, object]:
    if outlook_installed() and outlook_draft(subject, html):
        return {"method": "outlook", "cut": False}
    cut = default_mail_draft(subject, text, cut_note)
    return {"method": "default", "cut": cut}
