"""System tray icon and notifications, straight on the Win32 API (ctypes; no extra package).

The icon lives in its own thread with a hidden window and a message loop:

* left click (or Enter) opens the window; right click shows the menu:
  status line, "Open World Signal", "Scan now", "Quit";
* :meth:`Tray.notify` shows a Windows notification (balloon; Windows 10/11 show it as a toast);
  clicking it calls ``on_notification_click`` with the story it was about;
* if Explorer restarts, the icon is added again (``TaskbarCreated``).

Other threads call :meth:`notify`, :meth:`set_tooltip` and :meth:`stop`; they only post messages
or call the thread-safe ``Shell_NotifyIconW``.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_NULL = 0x0000
WM_CONTEXTMENU = 0x007B
WM_LBUTTONUP = 0x0202
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
NIN_SELECT = 0x0400
NIN_KEYSELECT = 0x0401
NIN_BALLOONUSERCLICK = 0x0405
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x10, 0x80
NOTIFYICON_VERSION_4 = 4
NIIF_USER, NIIF_LARGE_ICON, NIIF_RESPECT_QUIET_TIME = 0x4, 0x20, 0x80
MF_STRING, MF_GRAYED, MF_SEPARATOR = 0x0, 0x1, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
IDI_APPLICATION = 32512
SM_CXSMICON, SM_CXICON = 49, 11

CMD_OPEN, CMD_SCAN, CMD_QUIT = 1, 2, 3

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


def _api() -> tuple[ctypes.WinDLL, ctypes.WinDLL, ctypes.WinDLL]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    user32.LoadIconW.restype = wintypes.HICON
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      wintypes.HWND, wintypes.LPVOID]
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    return user32, shell32, kernel32


class Tray:
    def __init__(
        self,
        tooltip: str,
        icon_path: Path | None,
        *,
        on_open: Callable[[], None],
        on_scan: Callable[[], None],
        on_quit: Callable[[], None],
        on_notification_click: Callable[[int | None], None],
        menu_texts: Callable[[], dict[str, str]],
        status_line: Callable[[], str],
    ) -> None:
        self.tooltip = tooltip[:127]
        self.icon_path = icon_path
        self.on_open = on_open
        self.on_scan = on_scan
        self.on_quit = on_quit
        self.on_notification_click = on_notification_click
        self.menu_texts = menu_texts
        self.status_line = status_line
        self.hwnd: int | None = None
        self.last_story_id: int | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._wndproc = WNDPROC(self._proc)  # kept alive for the window's lifetime
        self._taskbar_created = 0
        self.added = False

    # -- public (any thread) ----------------------------------------------------------------------
    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.added

    def notify(self, title: str, body: str, story_id: int | None = None) -> bool:
        if self.hwnd is None:
            return False
        self.last_story_id = story_id
        nid = self._nid(NIF_INFO)
        nid.szInfoTitle = title[:63]
        nid.szInfo = body[:255] or " "
        nid.dwInfoFlags = NIIF_USER | NIIF_LARGE_ICON | NIIF_RESPECT_QUIET_TIME
        nid.hBalloonIcon = self._large_icon
        return bool(self._shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)))

    def set_tooltip(self, text: str) -> None:
        self.tooltip = text[:127]
        if self.hwnd is not None:
            nid = self._nid(NIF_TIP | NIF_SHOWTIP)
            self._shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def stop(self) -> None:
        if self.hwnd is not None:
            self._user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=5)

    # -- thread ------------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._user32, self._shell32, kernel32 = _api()
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASSEXW()
            cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
            cls.lpfnWndProc = self._wndproc
            cls.hInstance = hinst
            cls.lpszClassName = f"WorldSignalTray{id(self)}"
            if not self._user32.RegisterClassExW(ctypes.byref(cls)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.hwnd = self._user32.CreateWindowExW(0, cls.lpszClassName, "World Signal", 0, 0, 0, 0, 0,
                                                     None, None, hinst, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._taskbar_created = self._user32.RegisterWindowMessageW("TaskbarCreated")
            self._small_icon = self._load_icon(self._user32.GetSystemMetrics(SM_CXSMICON))
            self._large_icon = self._load_icon(self._user32.GetSystemMetrics(SM_CXICON))
            self._add()
        except OSError:
            log.exception("System tray icon could not be created")
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))
        self.hwnd = None

    def _load_icon(self, size: int) -> int:
        if self.icon_path is not None and self.icon_path.is_file():
            handle = self._user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if handle:
                return handle
        return self._user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    def _nid(self, flags: int) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._small_icon
        nid.szTip = self.tooltip
        return nid

    def _add(self) -> None:
        nid = self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        self.added = bool(self._shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        nid.uVersion = NOTIFYICON_VERSION_4
        self._shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
        if not self.added:
            log.warning("Shell_NotifyIcon(NIM_ADD) failed")

    def _menu(self) -> None:
        texts = self.menu_texts()
        menu = self._user32.CreatePopupMenu()
        try:
            self._user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, self.status_line())
            self._user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            self._user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, texts["open"])
            self._user32.AppendMenuW(menu, MF_STRING, CMD_SCAN, texts["scan"])
            self._user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            self._user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, texts["quit"])
            pt = wintypes.POINT()
            self._user32.GetCursorPos(ctypes.byref(pt))
            self._user32.SetForegroundWindow(self.hwnd)  # otherwise the menu does not close on outside clicks
            cmd = self._user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0,
                                              self.hwnd, None)
            self._user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            self._user32.DestroyMenu(menu)
        self._command(cmd)

    def _command(self, cmd: int) -> None:
        action = {CMD_OPEN: self.on_open, CMD_SCAN: self.on_scan, CMD_QUIT: self.on_quit}.get(cmd)
        if action is not None:
            self._safe(action)

    def _safe(self, fn: Callable[..., None], *args: object) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Tray action failed")

    def _proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, NIN_SELECT, NIN_KEYSELECT):
                self._safe(self.on_open)
            elif event == WM_CONTEXTMENU:
                self._menu()
            elif event == NIN_BALLOONUSERCLICK:
                self._safe(self.on_notification_click, self.last_story_id)
            return 0
        if msg == WM_COMMAND:
            self._command(wparam & 0xFFFF)
            return 0
        if msg == self._taskbar_created and msg:
            self._add()  # Explorer restarted: the icon must be added again
            return 0
        if msg == WM_CLOSE:
            nid = self._nid(0)
            self._shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self._user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            self._user32.PostQuitMessage(0)
            return 0
        return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)
