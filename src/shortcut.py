"""
Windows app identity, so clicking a notification can open the page.

Windows routes a toast click back to the app that posted it, identified by an
AppUserModelID. An unpackaged app — anything without an MSIX package, which
includes a repo you run with `python main.py` — has no identity of its own, so
Windows displays such a toast and then silently drops the click.

The only supported way to declare an AppUserModelID for an unpackaged app is a
Start Menu shortcut carrying the System.AppUserModel.ID property. That is not a
workaround; it is what every ordinary Windows installer does, and the reason it
usually goes unnoticed is that installers create a Start Menu shortcut anyway.

So this module writes one. `ensure()` runs at startup and is idempotent: it
only touches the file when the paths it should contain have changed, which
means moving or renaming the repo repairs itself the next time you start the
server rather than leaving a shortcut pointing at nothing.

A .lnk stores an absolute target — that is the file format, there is no
relative form — but nothing here is hardcoded. Every path is derived from
`__file__` and `sys.executable` at the moment the shortcut is written.

None of this is required for notifications to appear. Without the shortcut they
still show; only the click is lost. Every failure below is therefore soft.
"""

from __future__ import annotations

import os
import pathlib
import sys

AUMID = "machine-in-the-loop"
SHORTCUT_NAME = "Machine in the loop.lnk"

# Windows shows toasts posted under this built-in identity but drops the click.
# Used only when our own shortcut is absent, so notifications still arrive.
FALLBACK_AUMID = (
    r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def supported() -> bool:
    return sys.platform == "win32"


def shortcut_path() -> pathlib.Path:
    appdata = os.environ.get("APPDATA", "")
    return (
        pathlib.Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / SHORTCUT_NAME
    )


def _target() -> tuple[str, str]:
    """The interpreter to launch and its arguments, as of right now."""
    # pythonw runs the server without a console window; fall back to whatever
    # interpreter is running us if it is not alongside.
    executable = pathlib.Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    launcher = windowless if windowless.exists() else executable
    return str(launcher), f'"{REPO_ROOT / "main.py"}"'


def installed() -> bool:
    """True when a shortcut exists that points at this copy of the repo."""
    return supported() and shortcut_path().exists() and _matches_current_paths()


def aumid() -> str:
    """The identity to post toasts under. Ours if registered, else the fallback."""
    return AUMID if installed() else FALLBACK_AUMID


def _com_init() -> None:
    """
    Initialise COM for this thread, tolerating an existing initialisation.

    Deliberately never paired with CoUninitialize: tearing COM down after
    writing the shortcut broke every later call on the same thread, which
    surfaced as the banner claiming the shortcut was registered while the
    capability line insisted it was not.
    """
    import pythoncom

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass


def _shell_link():
    import pythoncom
    from win32com.shell import shell

    _com_init()
    return pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink,
    )


def _matches_current_paths() -> bool:
    """
    True when the existing shortcut points at this interpreter and this repo,
    and carries our identity. Anything else — a stale copy from a previous
    location, or someone else's file of the same name — counts as not ours.
    """
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon

        link = _shell_link()
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(shortcut_path()), 0)

        target, args = _target()
        # GetPath takes a single flags argument; 0 means the resolved path.
        if link.GetPath(0)[0].lower() != target.lower():
            return False
        if link.GetArguments() != args:
            return False

        store = link.QueryInterface(propsys.IID_IPropertyStore)
        return store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() == AUMID
    except Exception:
        # Unreadable, or pywin32 missing. Treat as "not ours" and fall back.
        return False


def _stale_case_name() -> pathlib.Path | None:
    """
    A shortcut differing from ours only by case.

    Windows paths are case-insensitive, so `exists()` is True for a file left
    over from an earlier spelling and writing over it does not necessarily
    correct the name shown in the Start Menu. Such a file has to be deleted
    before the new one is written.
    """
    folder = shortcut_path().parent
    if not folder.is_dir():
        return None
    for entry in folder.iterdir():
        if entry.name != SHORTCUT_NAME and entry.name.lower() == SHORTCUT_NAME.lower():
            return entry
    return None


def ensure() -> str:
    """
    Create or repair the shortcut. Returns a short status for the banner.

    Called on every startup. Writes only when something actually differs, so
    the Start Menu is not churned on each run.
    """
    if not supported():
        return "not needed on this platform"
    stale = _stale_case_name()
    if stale is None and shortcut_path().exists() and _matches_current_paths():
        return "registered"

    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
    except ImportError:
        return "pywin32 not installed — clicks will not open the page"

    target, args = _target()
    try:
        link = _shell_link()
        link.SetPath(target)
        link.SetArguments(args)
        link.SetWorkingDirectory(str(REPO_ROOT))
        link.SetDescription("Machine in the loop")

        # The part WScript.Shell cannot do, and the whole reason this module
        # exists: stamp the identity onto the shortcut.
        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(AUMID))
        store.Commit()

        shortcut_path().parent.mkdir(parents=True, exist_ok=True)
        if stale is not None:
            stale.unlink(missing_ok=True)
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(shortcut_path()), 0)
    except Exception as exc:  # noqa: BLE001 - never block startup over a shortcut
        return f"could not register ({type(exc).__name__}) — clicks will not open the page"

    return "registered"


def remove() -> str:
    if not supported():
        return "nothing to remove on this platform"
    path = shortcut_path()
    if not path.exists():
        return "no shortcut to remove"
    try:
        path.unlink()
    except OSError as exc:
        return f"could not remove {path}: {exc}"
    return f"removed {path}"
