# -*- coding: utf-8 -*-
"""
Aplicação de desktop - StudentPerfomance (Desempenho Académico e Hábitos de Estudo).

Uso:
    python desktop_app.py
"""
# IMPORTS
from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request

import uvicorn
import webview

from src.api import app as fastapi_app

# API - host e porta onde a API (e a interface web) vão correr. A interface é servida pela própria API.
API_HOST = "127.0.0.1"
API_PORT = 8000
APP_URL = f"http://{API_HOST}:{API_PORT}"

# Se a porta já estiver aberta, significa que a API ja está a correr, apenas abrindo a janela. Senão estiver aberta, corre o API num thread próprio, e depois abre a janela.
def _port_already_open(host: str, port: int) -> bool: # Verifica se a porta já está aberta.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock: # Cria um socket TCP/IP
        sock.settimeout(0.5) # Define um timeout de 0.5 segundos para a conexão
        return sock.connect_ex((host, port)) == 0 # Tenta conectar ao host e porta especificados. Se a conexão for bem sucedida, retorna True (porta aberta), senão retorna False (porta fechada)

# Servidor da API num thread próprio. O API serve a interface web (HTML,CSS,JS) e também fornece endpoints para a interface interagir com o backend (BD, análises, modelos).
def _run_api_server():
    # Corre a API (e a interface, servida pela própria API) num thread próprio.
    config = uvicorn.Config(fastapi_app, host=API_HOST, port=API_PORT, log_level="warning") # Configura o servidor Uvicorn com a aplicação FastAPI, host, porta e nível de log.
    server = uvicorn.Server(config) # Cria o servidor Uvicorn com a confuguração especificada.
    server.run() # Inicia o servidor Uvicorn, que corre a API e serve a interface web.

# Espera até a API estar pronta, verificando o endepoint /health. Se a API não estiver pronta dentro do timeout, retorna False.
def _wait_until_ready(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout # Define o tempo limite para esperar pela API (tempo atual + timeout)
    while time.time() < deadline: # Equanto o tempo atual for menor que o tempo limite, tenta verificar se a API está pronta.
        try: # Tenta abrir o endpoint. Se a API estiver pronta retorna True, senão espera 0.3s e tenta novamente.
            urllib.request.urlopen(f"{APP_URL}/health", timeout=1) # Tenta abrir o endpoint /health da API com timeout de 1 segundo. Se estiver pronta, retorna True. Se não estiver pronta, lança uma exceção.
            return True # Se estiver pronta, retorna True
        except Exception: # Exceção se a API não estiver pronta, espera 0.3s e tenta novamente.
            time.sleep(0.3) # Espera 0.3 segundos antes de tentar novamente
    return False # Se a API não estiver pronta dentro do timeout, retorna False.

# Função Principal da aplicação de desktop. Se a API não estiver a correr, corre-a num thread próprio, e depois abre a janela com a interface web.
def main():
    if not _port_already_open(API_HOST, API_PORT): # Se a porta não estiver pronta, corre a API num thread próprio. Senão estiver pronta, apenas abre a janela com a interface web.
        thread = threading.Thread(target=_run_api_server, daemon=True) # Cria a thread para correr a API num thread próprio, com target a função _run_api_server e daemon=True para que a thread seja terminada quando o programa principal terminar.
        thread.start() # Inicia a thread para correr a API num thread próprio.
        if not _wait_until_ready(): # Espera até a API estar pronta, verificando o endepoint /health. Se a API não estiver pronta dentro do timeout, exibe uma mensagem de erro e termina a execução.
            print("Aviso: a API demorou a arrancar, a janela pode demorar a mostrar dados.") # Aviso

    # Por omissão, o pywebview bloqueia downloads de ficheiros (definição
    # ALLOW_DOWNLOADS = False) — sem isto, botões como "Gerar PDF" (Fichas de
    # Desempenho), o ZIP de fichas em lote, ou o exportar CSV, não fazem
    # nada visível na janela da app, mesmo funcionando bem no browser.
    webview.settings["ALLOW_DOWNLOADS"] = True

    webview.create_window( # Cria a janela com a interface web, com título, URL, tamanho e outras confurações.
        "StudentPerfomance - Desempenho Académico e Hábitos de Estudo",
        url=APP_URL,
        width=1320,
        height=840,
        min_size=(1024, 650),
        text_select=True,
    )

# Se estiver a correr no Windows, tenta abrir a janela com o motor moderno (Edge WebView2). Se não estiver instalado, exibe uma mensagem de erro e instruções para instalar.
    if sys.platform.startswith("win"):
        try:
            webview.start(gui="edgechromium")
        except Exception as exc:
            print(
                "\nNão foi possível abrir a janela com o motor moderno (Edge WebView2).\n"
                "Isto normalmente significa que o 'WebView2 Runtime' não está instalado.\n"
                "Descarrega-o (gratuito, da Microsoft) em:\n"
                "  https://developer.microsoft.com/microsoft-edge/webview2/\n"
                "Depois de instalado, volta a correr 'python desktop_app.py'.\n"
                f"(detalhe técnico: {exc})\n"
            )
            input("Prime Enter para sair...")
            sys.exit(1)
    else:
        webview.start()

# Se o script for executado diretamente (não import), chama a função main() para iniciar a aplicação de desktop.
if __name__ == "__main__":
    main()
