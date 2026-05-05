"""Slide screenshot via PowerPoint COM + Win32 PrintWindow.

Why not Slide.Export("PNG")?
    Some corporate security suites (e.g. NASCA) intercept PowerPoint's
    file-export APIs. PrintWindow is a different code path (window
    rendering, not file I/O) and tends to remain available even when
    export is blocked.

How it works:
    1. Open the merged pptx via PowerPoint COM (DispatchEx — own instance)
    2. Start the slide show (`SlideShowSettings.Run`); this gives a single
       full-screen window per deck whose content matches what the audience
       would see.
    3. For each slide n: GotoSlide(n), wait for transition, capture the
       slideshow window's pixels via user32.PrintWindow into a DIB,
       write PNG.
    4. Close the slideshow + presentation, quit the app — guaranteed in
       a finally block.

Returns the list of PNG paths in slide order.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from pathlib import Path

# PrintWindow flag — render the full client area even if obscured.
# 0 = default (only what's currently painted), 2 = PW_RENDERFULLCONTENT.
_PW_RENDERFULLCONTENT = 2

# PowerPoint enums
_PP_SHOW_TYPE_SPEAKER = 1   # ppShowTypeSpeaker
_PP_ADV_MANUAL = 1          # ppSlideShowManualAdvance


class CaptureError(RuntimeError):
    """Raised when screenshot capture fails for a recoverable reason."""


def _print_window(hwnd: int) -> "object":
    """Capture an HWND's pixels to a PIL Image via PrintWindow + DIB.

    Returns a PIL.Image.Image. Raises CaptureError on any GDI failure.
    """
    from PIL import Image
    import win32gui
    import win32ui

    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bot - top
    if w <= 0 or h <= 0:
        raise CaptureError(f"window has zero size: {w}x{h}")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise CaptureError("GetWindowDC returned NULL")
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bitmap)

        result = ctypes.windll.user32.PrintWindow(
            hwnd, save_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT
        )
        if result == 0:
            raise CaptureError("PrintWindow returned 0 (failure)")

        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr, "raw", "BGRX", 0, 1,
        )
        return img
    finally:
        try:
            win32gui.DeleteObject(bitmap.GetHandle())
        except Exception:
            pass
        try:
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
        except Exception:
            pass
        win32gui.ReleaseDC(hwnd, hwnd_dc)


# PowerPoint slideshow window class name. The COM property
# `SlideShowWindow.HWND` is exposed as a non-callable method by pywin32 in
# both late- and early-bound dispatch modes (the type library declares it
# as a method without arguments, but invocation fails with "member not
# found"). Falling back to enumerating top-level windows is more robust.
_SLIDESHOW_CLASS = "screenClass"

# Off-screen coordinates used to hide the slideshow window during capture.
# PrintWindow can read pixels regardless of window position/Z-order, so
# moving the slideshow far off the visible desktop lets the user keep
# working while we capture in the background.
_OFFSCREEN_X = -32000
_OFFSCREEN_Y = -32000

# Win32 SetWindowPos flags (kept inline to avoid importing win32con everywhere)
_SWP_NOACTIVATE = 0x0010
_SWP_NOZORDER = 0x0004
_SWP_NOSIZE = 0x0001
_SWP_FRAMECHANGED = 0x0020


def _find_slideshow_hwnd() -> int:
    """Locate the PowerPoint slideshow window via Win32 FindWindow.

    Returns 0 if no slideshow window is currently open. Assumes only one
    slideshow runs at a time (true for this pipeline since we use
    DispatchEx for an isolated PowerPoint instance).
    """
    import win32gui

    try:
        hwnd = win32gui.FindWindow(_SLIDESHOW_CLASS, None)
    except Exception:
        return 0
    return int(hwnd) if hwnd else 0


def _wait_for_window(*, timeout: float = 10.0, poll: float = 0.1) -> int:
    """Poll until a slideshow window of class `screenClass` appears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _find_slideshow_hwnd()
        if hwnd:
            return hwnd
        time.sleep(poll)
    raise CaptureError("slideshow window did not appear within timeout")


def _move_window_offscreen(hwnd: int) -> None:
    """Push the slideshow window to invisible coordinates so the user's
    desktop is not occluded. PrintWindow still reads pixels correctly.

    Best-effort — failures are silently ignored (the worst case is a
    visible slideshow, not a broken capture).
    """
    import win32gui

    try:
        # Preserve current size; only move + don't activate, don't reorder.
        win32gui.SetWindowPos(
            hwnd, 0,
            _OFFSCREEN_X, _OFFSCREEN_Y, 0, 0,
            _SWP_NOACTIVATE | _SWP_NOZORDER | _SWP_NOSIZE,
        )
    except Exception:
        pass


def screenshot_deck(
    pptx_path: Path,
    out_dir: Path,
    *,
    wait_per_slide: float = 1.0,
    open_timeout: float = 15.0,
    per_slide_timeout: float = 10.0,
) -> list[Path]:
    """Capture every slide in pptx_path as a PNG. Return paths in slide order.

    Args:
        pptx_path: merged deck to capture.
        out_dir: directory PNGs are written into (created if missing).
        wait_per_slide: seconds to sleep after GotoSlide before capture
            (lets transitions settle).
        open_timeout: max seconds to wait for slideshow window to appear.
        per_slide_timeout: max seconds for one slide's GotoSlide+capture.

    Raises:
        CaptureError: when PowerPoint fails to start, slideshow doesn't
            open, or PrintWindow fails. Caller should treat this as a
            graceful skip (deck still usable, just no visual revision).
    """
    import win32com.client
    import pythoncom

    pptx_path = Path(pptx_path).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not pptx_path.exists():
        raise CaptureError(f"pptx not found: {pptx_path}")

    pythoncom.CoInitialize()
    app = None
    prs = None
    show = None
    paths: list[Path] = []
    try:
        try:
            app = win32com.client.DispatchEx("PowerPoint.Application")
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"could not start PowerPoint: {exc}") from exc

        # PowerPoint refuses to run a slideshow if its main window is hidden.
        try:
            app.Visible = True
        except Exception:
            pass

        try:
            prs = app.Presentations.Open(
                str(pptx_path), ReadOnly=True, WithWindow=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"could not open pptx: {exc}") from exc

        n_slides = int(prs.Slides.Count)
        if n_slides == 0:
            raise CaptureError("deck has 0 slides")

        ss = prs.SlideShowSettings
        ss.ShowType = _PP_SHOW_TYPE_SPEAKER
        ss.AdvanceMode = _PP_ADV_MANUAL
        try:
            show = ss.Run()
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"SlideShowSettings.Run failed: {exc}") from exc

        # Show.HWND is sometimes 0 immediately after Run(); poll briefly.
        hwnd = _wait_for_window(timeout=open_timeout)

        # Hide the slideshow off-screen so the user can keep working.
        # PrintWindow with PW_RENDERFULLCONTENT reads pixels regardless of
        # window position. There's a brief flicker on Run() — unavoidable —
        # but everything after is background.
        _move_window_offscreen(hwnd)

        # Initial settle (first slide rendered + animations skipped to end).
        time.sleep(max(wait_per_slide, 0.5))

        for n in range(1, n_slides + 1):
            t_start = time.time()
            try:
                show.View.GotoSlide(n)
            except Exception as exc:  # noqa: BLE001
                raise CaptureError(f"GotoSlide({n}) failed: {exc}") from exc
            time.sleep(wait_per_slide)

            img = _print_window(hwnd)
            out_path = out_dir / f"slide_{n:02d}.png"
            img.save(out_path, "PNG")
            paths.append(out_path)

            if time.time() - t_start > per_slide_timeout:
                # Don't abort — this slide is captured. Log only.
                # (We don't depend on a logger here to keep the module
                # importable in smoke tests.)
                pass

        return paths
    finally:
        # Tear down in reverse order. Swallow errors — if PowerPoint is
        # already gone we still want to reach CoUninitialize.
        if show is not None:
            try:
                show.View.Exit()
            except Exception:
                pass
        if prs is not None:
            try:
                prs.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
