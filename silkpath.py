import threading
from queue import Queue
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from pathlib import Path
from collections import defaultdict
from rich import print
from rich.console import Console
from rich.tree import Tree
from random import choice
import requests
import argparse

# Variáveis globais
visited = set()
lock = threading.Lock()
queue = Queue()

domain_base = ''
exclude_paths = []
user_agents = []

HEADER = {}
PATHS = []
FILES = []
URLS = []

def build_url_tree(urls):
    root = {}
    for url in urls:
        parsed = urlparse(url)
        parts = parsed.path.strip('/').split('/')
        current = root
        for part in parts:
            if part:
                current = current.setdefault(part, {})
    return root

def render_tree(tree_dict, rich_tree):
    for key, subtree in sorted(tree_dict.items()):
        branch = rich_tree.add(f"[green]{key}/")
        render_tree(subtree, branch)

def print_url_tree(urls):
    print("\n[bold blue]Estrutura do site (Sitemap):[/bold blue]\n")
    parsed_root = urlparse(urls[0])
    domain = parsed_root.netloc
    tree_data = build_url_tree(urls)
    
    root_tree = Tree(f"[bold white]{domain}/[/bold white]")
    render_tree(tree_data, root_tree)
    print(root_tree)

def print_logo():
    console = Console()
    logo = """[bold blue]
    ╔════════════════════════════════════════════╗
    ║               🕷  [bright_magenta]SILKPATH[/bright_magenta] 🕸              ║
    ║  [cyan]Silent crawler spinning through the web[/cyan]   ║
    ╚════════════════════════════════════════════╝[/bold blue]

           [white]\\     .--.
            \\   |o_o |     [grey]Teia conectando links...[/grey]
                |:_/ |     [grey]Explorando caminhos ocultos.[/grey]
               //   \\ \\
              (|     | )
             /'\\_   _/`\\
             \\___)=(___/

[bold white]  Author:[/] Wesley Ruan
[bold white]  GitHub:[/] [dim][seu usuário aqui][/dim]
[bold white]  Desc  :[/] Multithreaded web crawler for reconnaissance
[bold blue]----------------------------------------------------------[/bold blue]
"""
    console.print(logo)

def test_url(url):
    try:
        if user_agents:
            HEADER['User-Agent'] = choice(user_agents)
        response = requests.get(url, headers=HEADER, timeout=5, allow_redirects=True)
        if response.status_code == 200 and url not in URLS:
            URLS.append(url)
            return response
    except requests.RequestException:
        pass
    return None

def get_content(response):
    return response.text

def create_soup(html):
    soup = BeautifulSoup(html, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True)]

def normalize_url(base, link):
    return urljoin(base, link)

def get_directory_chain(url):
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    urls = []
    for i in range(len(parts), 0, -1):
        new_path = '/'.join(parts[:i]) + '/'
        full_url = f"{parsed.scheme}://{parsed.netloc}/{new_path}"
        urls.append(full_url)
    return urls

def worker(cookie, max_depth):
    print(f"[cyan]Thread {threading.current_thread().name} iniciou...[/cyan]")
    while True:
        try:
            url, depth = queue.get(timeout=5)
        except:
            break

        with lock:
            if url in visited or depth > max_depth:
                queue.task_done()
                continue
            visited.add(url)

        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        if domain != domain_base:
            queue.task_done()
            continue

        if exclude_paths and parsed_url.path in exclude_paths:
            queue.task_done()
            continue

        response = test_url(url)
        if not response:
            queue.task_done()
            continue

        path = Path(parsed_url.path)
        extension = path.suffix
        if extension and parsed_url.path not in FILES:
            FILES.append(parsed_url.path)
        else:
            if parsed_url.path not in PATHS:
                PATHS.append(parsed_url.path)

        html = get_content(response)
        print(f"[green][+] Visitando:[/] {url}")
        hrefs = create_soup(html)

        for href in hrefs:
            full_link = normalize_url(url, href)
            print("\t| [yellow][!] Encontrado:[/] ", full_link)
            queue.put((full_link, depth + 1))

        for parent_url in get_directory_chain(url):
            queue.put((parent_url, depth + 1))

        queue.task_done()

if __name__ == "__main__":
    print_logo()

    parser = argparse.ArgumentParser(description="Crawler recursivo com controle de threads.")
    parser.add_argument("-u", "--url", required=True, help="URL base")
    parser.add_argument("-t", "--threads", type=int, default=10, help="Número de threads")
    parser.add_argument("-c", "--cookie", help="Cookie (formato: chave=valor;...)", default=None)
    parser.add_argument("-ep", "--exclude_paths", nargs='*', required=False)
    parser.add_argument("-a", "--user-agent", help="User-Agent (formato: string)", default=None)
    parser.add_argument("-ra", "--random-agent", help="User agent aleatório a cada requisição", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    args = parser.parse_args()

    max_depth = 3

    # Headers e user agents
    if args.user_agent:
        HEADER['User-Agent'] = args.user_agent
    elif args.random_agent:
        with open("user-agents.txt", 'r') as f:
            user_agents = [line.strip() for line in f.readlines()]

    queue.put((args.url, 0))
    parsed_url = urlparse(args.url)
    domain_base = parsed_url.netloc
    exclude_paths = args.exclude_paths or []

    # Iniciar threads
    threads = []
    for _ in range(args.threads):
        thread = threading.Thread(target=worker, args=(args.cookie, max_depth))
        thread.start()
        threads.append(thread)

    # Esperar a fila esvaziar
    queue.join()

    # Esperar todas as threads finalizarem
    for thread in threads:
        thread.join()

    print_url_tree(URLS)
    print("\n[✓] Fim do scan.")
