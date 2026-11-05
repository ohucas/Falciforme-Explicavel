from pathlib import Path
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

RAIZ = Path(__file__).resolve().parent


def porta_disponivel():
    """Solicita ao sistema uma porta local livre para esta execução."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conexao:
        conexao.bind(("127.0.0.1", 0))
        return conexao.getsockname()[1]


def comando_servidor(porta):
    argumentos = ["--servidor", str(porta)]
    if getattr(sys, "frozen", False):
        return [sys.executable, *argumentos]
    return [sys.executable, str(RAIZ / "iniciar_app.py"), *argumentos]


def servidor_pronto(porta):
    # Ignora proxies corporativos apenas para verificar o próprio computador.
    cliente = build_opener(ProxyHandler({}))
    try:
        with cliente.open(
            f"http://127.0.0.1:{porta}/_stcore/health", timeout=0.3
        ) as resposta:
            return resposta.status == 200 and resposta.read(16).strip() == b"ok"
    except (URLError, OSError, TimeoutError):
        return False


def iniciar_servidor(porta):
    # Executáveis Windows sem console não oferecem stdout/stderr por padrão.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    from streamlit.web import bootstrap

    os.chdir(RAIZ)
    # Cada instância recebe uma porta e não publica serviço na rede do consultório.
    opcoes = {
        "server.address": "127.0.0.1",
        "server.port": porta,
        "server.headless": True,
        "server.fileWatcherType": "none",
        "server.runOnSave": False,
        "server.enableXsrfProtection": True,
        "server.enableCORS": True,
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }
    bootstrap.load_config_options(opcoes)
    bootstrap.run(str(RAIZ / "app.py"), False, [], opcoes)


def encerrar_processo(processo):
    if processo is None or processo.poll() is not None:
        return
    processo.terminate()
    try:
        processo.wait(timeout=5)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait(timeout=5)


def iniciar_janela():
    import tkinter as tk
    from tkinter import messagebox, ttk

    janela = tk.Tk()
    janela.title("Falciforme Explicável")
    janela.geometry("510x300")
    janela.resizable(False, False)
    icone = RAIZ / "assets" / "icone.png"
    if icone.is_file():
        imagem = tk.PhotoImage(file=str(icone))
        janela.iconphoto(True, imagem)
        janela.icone = imagem

    quadro = ttk.Frame(janela, padding=24)
    quadro.pack(fill="both", expand=True)
    ttk.Label(
        quadro,
        text="Falciforme Explicável",
        font=("Arial", 18, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        quadro,
        text="Acompanhamento longitudinal para avaliação médica",
    ).pack(anchor="w", pady=(6, 18))
    estado = tk.StringVar(value="Iniciando o atendimento local…")
    ttk.Label(quadro, textvariable=estado, wraplength=455).pack(anchor="w")
    endereco = tk.StringVar()
    ttk.Label(quadro, textvariable=endereco).pack(anchor="w", pady=(6, 12))
    porta = porta_disponivel()
    url = f"http://127.0.0.1:{porta}"
    processo = None
    encerrando = False
    pronto = False
    inicio = time.monotonic()

    def abrir():
        if not webbrowser.open(url):
            messagebox.showinfo(
                "Abrir atendimento",
                f"Abra seu navegador e acesse:\n{url}",
                parent=janela,
            )

    def encerrar():
        nonlocal encerrando
        if encerrando:
            return
        if pronto and not messagebox.askyesno(
            "Encerrar aplicativo",
            "Encerrar o atendimento local? Exporte o PDF antes de sair. "
            "Os dados desta sessão não serão mantidos pelo aplicativo.",
            parent=janela,
        ):
            return
        encerrando = True
        encerrar_processo(processo)
        janela.destroy()

    abrir_botao = ttk.Button(quadro, text="Abrir atendimento", command=abrir)
    abrir_botao.pack(fill="x", pady=(0, 8))
    abrir_botao.state(["disabled"])
    ttk.Button(quadro, text="Encerrar aplicativo", command=encerrar).pack(fill="x")
    janela.protocol("WM_DELETE_WINDOW", encerrar)

    def verificar():
        nonlocal pronto
        if encerrando:
            return
        if processo.poll() is not None:
            estado.set(
                "Não foi possível manter o aplicativo em execução. Feche e tente novamente."
            )
            abrir_botao.state(["disabled"])
            return
        if not pronto and servidor_pronto(porta):
            pronto = True
            estado.set(
                "Aplicativo em execução. Mantenha esta janela aberta durante o uso."
            )
            endereco.set(url)
            abrir_botao.state(["!disabled"])
            abrir()
        elif not pronto and time.monotonic() - inicio > 90:
            encerrar_processo(processo)
            estado.set(
                "A inicialização demorou mais que o esperado. Feche e tente novamente."
            )
            return
        janela.after(700, verificar)

    try:
        opcoes = {}
        if os.name == "nt":
            opcoes["creationflags"] = subprocess.CREATE_NO_WINDOW
        # Sem logs clínicos em disco. Erros de inicialização ficam na janela.
        processo = subprocess.Popen(
            comando_servidor(porta),
            cwd=RAIZ,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **opcoes,
        )
        janela.after(300, verificar)
        janela.mainloop()
    except OSError:
        messagebox.showerror(
            "Falha ao iniciar",
            "Não foi possível iniciar o aplicativo local. "
            "Confira se a instalação está completa e tente novamente.",
            parent=janela,
        )
    finally:
        encerrar_processo(processo)


if __name__ == "__main__":
    # Necessário também para subprocessos de bibliotecas em executáveis.
    import multiprocessing

    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--servidor":
        porta = int(sys.argv[2])
        if not 1024 <= porta <= 65535:
            raise ValueError("Porta local inválida.")
        iniciar_servidor(porta)
    else:
        iniciar_janela()
