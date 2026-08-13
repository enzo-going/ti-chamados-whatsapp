"""Aplicativo local para abrir e demonstrar o helpdesk no Windows.

O controlador mantém o servidor restrito a ``127.0.0.1``, abre o painel no
navegador e permite simular mensagens sem conectar uma conta de WhatsApp. O
banco fica fora da pasta de instalação, em dados locais do usuário, para
sobreviver a atualizações do executável.
"""

from __future__ import annotations

import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request
import webbrowser

from helpdesk.demo import send_message
from helpdesk.http_app import _build_gateway, make_server


APP_DIRECTORY_NAME = "TIChamadosWhatsApp"
DATABASE_FILE_NAME = "chamados.sqlite3"
LOG_FILE_NAME = "aplicativo.log"
_MUTEX_NAME = r"Local\TIChamadosWhatsApp"
_ERROR_ALREADY_EXISTS = 183

logger = logging.getLogger(__name__)


def default_data_directory() -> Path:
    """Pasta persistente do aplicativo para o usuário atual."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIRECTORY_NAME
    return Path.home() / f".{APP_DIRECTORY_NAME}"


def configure_file_logging(data_directory: Path) -> Path:
    """Ativa log rotativo local e devolve o caminho do arquivo."""

    log_directory = data_directory / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / LOG_FILE_NAME

    root_logger = logging.getLogger()
    resolved = log_path.resolve()
    already_configured = any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == resolved
        for handler in root_logger.handlers
    )
    if not already_configured:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root_logger.addHandler(handler)
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    return log_path


class DesktopServer:
    """Ciclo de vida do servidor local usado pelo aplicativo gráfico."""

    def __init__(self, data_directory: Path | None = None) -> None:
        self.data_directory = data_directory or default_data_directory()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.database_path = self.data_directory / DATABASE_FILE_NAME

        gateway, repository = _build_gateway(str(self.database_path))
        self.repository = repository

        self._server = make_server(gateway, self.repository, "127.0.0.1", 0)
        host, port = self._server.server_address[:2]
        self.host = str(host)
        self.port = int(port)
        self._thread: threading.Thread | None = None
        self._stopped = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def dashboard_url(self) -> str:
        return f"{self.base_url}/dashboard"

    def start(self) -> None:
        if self._stopped:
            raise RuntimeError("O servidor já foi encerrado.")
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ti-chamados-http",
            daemon=True,
        )
        self._thread.start()
        logger.info("Aplicativo local iniciado em 127.0.0.1, porta %s.", self.port)

    def simulate_message(self, text: str) -> dict:
        """Envia uma mensagem fictícia ao fluxo HTTP local."""

        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError("O servidor local não está em execução.")
        return send_message(text, base_url=self.base_url)

    def open_ticket_count(self) -> int:
        return len(self.repository.list_open())

    def stop(self) -> None:
        if self._stopped:
            return
        if self._thread is not None and self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()
        self.repository.close()
        self._stopped = True
        logger.info("Aplicativo local encerrado.")

    def __enter__(self) -> "DesktopServer":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


class _SingleInstanceGuard:
    """Mutex do Windows para evitar duas instâncias sobre o mesmo banco."""

    def __init__(self) -> None:
        self.handle: int | None = None
        self.already_running = False

    def acquire(self) -> None:
        if os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            raise OSError(
                ctypes.get_last_error(), "Não foi possível iniciar o aplicativo."
            )
        self.handle = int(handle)
        self.already_running = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS

    def release(self) -> None:
        if self.handle is None or os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(ctypes.c_void_p(self.handle))
        self.handle = None


def _show_error(title: str, message: str) -> None:
    """Exibe uma mensagem mesmo quando o executável não tem console."""

    try:
        from tkinter import messagebox

        messagebox.showerror(title, message)
    except Exception:
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)


def _run_window(server: DesktopServer) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("TI Chamados WhatsApp")
    root.geometry("560x360")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="TI Chamados WhatsApp",
        font=("Segoe UI", 18, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        frame,
        text="Demonstração local — sem conexão com WhatsApp real",
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(2, 18))

    status_var = tk.StringVar()

    def refresh_status(prefix: str = "Servidor local ativo") -> None:
        count = server.open_ticket_count()
        plural = "s" if count != 1 else ""
        status_var.set(f"{prefix} · {count} chamado{plural} em aberto")

    ttk.Label(frame, textvariable=status_var, font=("Segoe UI", 10)).pack(
        anchor="w"
    )
    refresh_status("Dados locais carregados")

    ttk.Button(
        frame,
        text="Abrir painel",
        command=lambda: webbrowser.open(server.dashboard_url),
    ).pack(fill="x", pady=(18, 16))

    ttk.Label(frame, text="Simular uma mensagem recebida:").pack(anchor="w")
    message_var = tk.StringVar()
    message_entry = ttk.Entry(frame, textvariable=message_var)
    message_entry.pack(fill="x", pady=(5, 8))

    def simulate(*_args: object) -> None:
        text = message_var.get().strip()
        if not text:
            messagebox.showinfo("Mensagem vazia", "Digite uma mensagem para simular.")
            return
        try:
            result = server.simulate_message(text)
        except Exception:
            logger.exception("Falha ao simular uma mensagem local.")
            messagebox.showerror(
                "Não foi possível simular",
                "O servidor local não respondeu. Feche e abra o aplicativo novamente.",
            )
            return

        ticket_id = result.get("ticket_id", "?")
        outcome = result.get("outcome")
        labels = {
            "criado": "Novo chamado criado",
            "followup": "Follow-up anexado",
            "reaberto": "Chamado reaberto",
        }
        refresh_status(f"{labels.get(outcome, 'Mensagem registrada')} no #{ticket_id}")
        message_var.set("")

    ttk.Button(frame, text="Enviar simulação", command=simulate).pack(fill="x")
    message_entry.bind("<Return>", simulate)

    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=(22, 0))

    def open_data_directory() -> None:
        if os.name == "nt":
            os.startfile(server.data_directory)  # type: ignore[attr-defined]
        else:
            webbrowser.open(server.data_directory.resolve().as_uri())

    ttk.Button(actions, text="Abrir pasta de dados", command=open_data_directory).pack(
        side="left"
    )

    closing = False

    def close() -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        server.stop()
        root.destroy()

    ttk.Button(actions, text="Encerrar", command=close).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(300, lambda: webbrowser.open(server.dashboard_url))
    message_entry.focus_set()
    root.mainloop()


def run_smoke_test() -> None:
    """Valida o pacote sem abrir janela, navegador ou dados permanentes."""

    with tempfile.TemporaryDirectory(prefix="ti-chamados-smoke-") as temp_dir:
        with DesktopServer(Path(temp_dir)) as server:
            with urllib.request.urlopen(
                f"{server.base_url}/health", timeout=5
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        "A rota de saúde do pacote não respondeu corretamente."
                    )
            with urllib.request.urlopen(server.dashboard_url, timeout=5) as response:
                dashboard = response.read().decode("utf-8")
                if "Chamados em aberto" not in dashboard:
                    raise RuntimeError("O painel não foi encontrado no pacote.")
                if "Nenhum chamado em aberto." not in dashboard:
                    raise RuntimeError(
                        "O aplicativo empacotado não iniciou com o painel vazio."
                    )
            result = server.simulate_message("a impressora do setor parou")
            if result.get("outcome") != "criado":
                raise RuntimeError("A simulação do pacote não criou um chamado.")


def main() -> None:
    if "--smoke-test" in sys.argv:
        run_smoke_test()
        return

    guard = _SingleInstanceGuard()
    server: DesktopServer | None = None
    try:
        guard.acquire()
        if guard.already_running:
            _show_error(
                "TI Chamados WhatsApp",
                "O aplicativo já está aberto nesta sessão.",
            )
            return

        data_directory = default_data_directory()
        configure_file_logging(data_directory)
        server = DesktopServer(data_directory)
        server.start()
        _run_window(server)
    except Exception:
        logger.exception("Falha ao iniciar o aplicativo local.")
        _show_error(
            "TI Chamados WhatsApp",
            "Não foi possível iniciar o aplicativo. "
            "Consulte o arquivo de log na pasta de dados.",
        )
    finally:
        if server is not None:
            server.stop()
        guard.release()


if __name__ == "__main__":
    main()
