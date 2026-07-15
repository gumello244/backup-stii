"""Remos — Recuperação de Arquivos Pessoais.

Entry point: single-instance mutex, asyncio policy, QApplication,
MainWindow, global exception hook for crash reporting.

Example:
    python main.py
"""
import sys
import os
import asyncio
from PyQt5.QtWidgets import QApplication


def _setup_logging() -> None:
    """Configure structured console logging for the application."""
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _init_qapp() -> QApplication:
    """Initialize and configure the QApplication instance."""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QIcon
    from config import get_app_name
    from ui.assets import asset_path

    app = QApplication(sys.argv)
    app.setApplicationName(get_app_name())
    app.setOrganizationName("STII")
    app.setOrganizationDomain("pmc.local")

    icon_path = asset_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    return app


def main() -> None:
    """Launch the Remos application."""
    _setup_logging()
    mutex = _acquire_mutex()
    _set_asyncio_policy()
    _install_exception_hook()

    # Start the global async worker thread and send startup telemetry
    from ui.workers import get_global_worker
    get_global_worker()

    app = _init_qapp()
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    app.aboutToQuit.connect(_on_app_quit)
    sys.exit(app.exec_())


def _acquire_mutex() -> object:
    """Prevent multiple instances via a Windows named mutex.

    Example:
        mutex = _acquire_mutex()  # exits if another instance runs
    """
    if sys.platform != "win32":
        return None
    try:
        import win32event
        import win32api
        import winerror
        from config import get_app_name

        mutex = win32event.CreateMutex(
            None, False, f"Global\\{get_app_name()}_Instance_Lock",
        )
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            sys.exit(0)
        return mutex
    except ImportError:
        return None


def _set_asyncio_policy() -> None:
    """Use the Windows Selector event loop policy for compatibility.

    Example:
        _set_asyncio_policy()
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy(),
        )


def _install_exception_hook() -> None:
    """Install a global exception handler that reports crashes via API.

    Example:
        _install_exception_hook()
    """
    sys._excepthook = sys.excepthook

    def exception_hook(
        exc_type: type,
        exc_value: BaseException,
        exc_traceback: object,
    ) -> None:
        _report_crash(exc_type, exc_value, exc_traceback)
        sys._excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = exception_hook


def _report_crash(
    exc_type: type,
    exc_value: BaseException,
    exc_traceback: object,
) -> None:
    """Attempt to report a crash through the global worker."""
    try:
        from ui.workers import get_global_worker
        worker = get_global_worker()
        if worker and worker.api_service:
            coro = worker.api_service.report_crash(
                exc_type, exc_value, exc_traceback,
            )
            worker.submit_task(coro)
    except Exception:
        pass


def _on_app_quit() -> None:
    """Graceful shutdown: stop the global async worker and the elevated
    admin-restore helper, if one was started this run."""
    try:
        from ui.workers import get_global_worker
        worker = get_global_worker()
        if worker:
            worker.stop()
    except Exception:
        pass
    try:
        from services.elevation import shutdown_helper
        shutdown_helper()
    except Exception:
        pass


if __name__ == "__main__":
    from services.elevation import ADMIN_HELPER_FLAG
    if ADMIN_HELPER_FLAG in sys.argv:
        _setup_logging()
        from services.elevation import run_helper_server
        run_helper_server()
    else:
        main()
