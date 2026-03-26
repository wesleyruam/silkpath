import threading
import signal
import sys
import time
import random
import re
import ssl
import warnings
from queue import Queue, Empty
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup
from pathlib import Path
from collections import defaultdict, deque
from rich import print
from rich.console import Console
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.style import Style
from rich.color import Color
from datetime import datetime
from typing import Set, List, Dict, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context
import argparse
import logging
from dataclasses import dataclass, field
from enum import Enum

# Suprime warnings de SSL (opcional)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="ssl")

# Configuração de logging com formatação personalizada
class ColoredFormatter(logging.Formatter):
    """Formatter personalizado com cores para diferentes níveis de log"""
    
    # Cores para diferentes status codes HTTP
    STATUS_COLORS = {
        # 2xx - Success (Green)
        range(200, 300): ("green", "✓"),
        # 3xx - Redirect (Cyan)
        range(300, 400): ("cyan", "➡"),
        # 4xx - Client Error (Yellow/Red)
        400: ("yellow", "⚠"),
        401: ("yellow", "🔒"),
        403: ("red", "🚫"),
        404: ("yellow", "❓"),
        429: ("red", "🐌"),
        # 5xx - Server Error (Red)
        range(500, 600): ("red", "💥"),
    }
    
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.console = Console()
    
    def get_status_style(self, status_code: int) -> Tuple[str, str]:
        """Retorna a cor e ícone para um status code"""
        if 200 <= status_code < 300:
            return "green", "✓"
        elif 300 <= status_code < 400:
            return "cyan", "➡"
        elif status_code == 400:
            return "yellow", "⚠"
        elif status_code == 401:
            return "yellow", "🔒"
        elif status_code == 403:
            return "red", "🚫"
        elif status_code == 404:
            return "yellow", "❓"
        elif status_code == 429:
            return "red", "🐌"
        elif 500 <= status_code < 600:
            return "red", "💥"
        else:
            return "white", "•"
    
    def format(self, record):
        """Formata o registro de log com cores"""
        # Se for mensagem de requisição HTTP, tenta extrair status code
        if hasattr(record, 'status_code'):
            status = record.status_code
            color, icon = self.get_status_style(status)
            
            # Formata a mensagem com o status code colorido
            if hasattr(record, 'url'):
                record.msg = f"[{color}]{icon} {status}[/{color}] {record.url} - {record.msg}"
            else:
                record.msg = f"[{color}]{icon} {status}[/{color}] {record.msg}"
        
        # Formata os diferentes níveis de log
        if record.levelno == logging.WARNING:
            record.msg = f"[yellow]⚠ {record.msg}[/yellow]"
        elif record.levelno == logging.ERROR:
            record.msg = f"[red]✗ {record.msg}[/red]"
        elif record.levelno == logging.INFO:
            record.msg = f"[cyan]ℹ[/cyan] {record.msg}"
        
        return super().format(record)

class ColoredHandler(logging.StreamHandler):
    """Handler de logging com cores"""
    def __init__(self):
        super().__init__()
        self.console = Console()
    
    def emit(self, record):
        try:
            msg = self.format(record)
            # Usa Rich para imprimir com cores
            self.console.print(msg)
        except Exception:
            self.handleError(record)

# Configuração de logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Remove handlers existentes
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Adiciona handler colorido para console
console_handler = ColoredHandler()
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
logger.addHandler(console_handler)

# Adiciona handler para arquivo (sem cores)
file_handler = logging.FileHandler('crawler.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

class CrawlerStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"

class ProtectionType(Enum):
    NONE = "none"
    CLOUDFLARE = "cloudflare"
    DDOS_GUARD = "ddos_guard"
    INCAPSULA = "incapsula"
    SUCURI = "sucuri"
    AUTH_REQUIRED = "auth_required"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"

@dataclass
class ProtectionInfo:
    type: ProtectionType = ProtectionType.NONE
    detected: bool = False
    details: str = ""
    requires_cookie: bool = False
    requires_js: bool = False
    requires_captcha: bool = False
    challenge_page: bool = False

@dataclass
class CrawlerStats:
    total_urls: int = 0
    unique_urls: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_files: int = 0
    total_paths: int = 0
    blocked_by_robots: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    # Estatísticas por status code
    status_codes: Dict[int, int] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

class RateLimiter:
    def __init__(self, requests_per_second: float = 10):
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.min_interval:
                time.sleep(self.min_interval - time_since_last)
            self.last_request_time = time.time()

class ProxyManager:
    """Gerenciador de proxies com suporte a proxy rotativo"""
    
    def __init__(self, proxy_list: List[str] = None, proxy_file: str = None, 
                 rotate_proxy: bool = False, proxy_auth: str = None):
        self.proxies = []
        self.current_index = 0
        self.rotate_proxy = rotate_proxy
        self.lock = threading.Lock()
        self.proxy_auth = proxy_auth
        
        # Carrega proxies da lista
        if proxy_list:
            self.proxies.extend(proxy_list)
        
        # Carrega proxies do arquivo
        if proxy_file:
            self._load_proxies_from_file(proxy_file)
        
        if self.proxies:
            logger.info(f"Loaded {len(self.proxies)} proxies")
            for i, proxy in enumerate(self.proxies[:5]):  # Mostra apenas 5
                logger.debug(f"  Proxy {i+1}: {proxy}")
            if len(self.proxies) > 5:
                logger.debug(f"  ... and {len(self.proxies) - 5} more")
    
    def _load_proxies_from_file(self, file_path: str):
        """Carrega proxies de um arquivo"""
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Suporta formatos: ip:port, http://ip:port, https://ip:port
                        if not line.startswith('http'):
                            line = f"http://{line}"
                        self.proxies.append(line)
        except Exception as e:
            logger.error(f"Error loading proxies from file: {e}")
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Retorna um proxy no formato requests"""
        if not self.proxies:
            return None
        
        with self.lock:
            if self.rotate_proxy:
                # Rotativo - pega próximo proxy
                proxy_url = self.proxies[self.current_index % len(self.proxies)]
                self.current_index += 1
            else:
                # Fixo - sempre o primeiro
                proxy_url = self.proxies[0]
            
            # Adiciona autenticação se necessário
            if self.proxy_auth and '@' not in proxy_url:
                # Formato: http://user:pass@ip:port
                proxy_url = proxy_url.replace('://', f'://{self.proxy_auth}@')
            
            return {'http': proxy_url, 'https': proxy_url}
    
    def get_proxy_info(self) -> str:
        """Retorna informações sobre o proxy atual"""
        if not self.proxies:
            return "No proxy configured"
        
        if self.rotate_proxy:
            return f"Rotating proxy (total: {len(self.proxies)})"
        else:
            return f"Fixed proxy: {self.proxies[0]}"

class CustomHTTPAdapter(HTTPAdapter):
    """Adapter HTTP personalizado para simular TLS fingerprint de navegador"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384')
        # Remove opções SSL/TLS deprecated
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        # TLS 1.0 e 1.1 ainda são usados, mantemos
        # context.options |= ssl.OP_NO_TLSv1
        # context.options |= ssl.OP_NO_TLSv1_1
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class WebCrawler:
    def __init__(self, base_url: str, max_depth: int = 3, max_threads: int = 10,
                 timeout: int = 15, max_retries: int = 3, rate_limit: float = 5,
                 respect_robots: bool = False, user_agent: str = None,
                 max_idle_time: int = 30, proxy_manager: ProxyManager = None):
        
        self.base_url = base_url
        self.original_base_url = base_url
        self.domain_base = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_threads = max_threads
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_idle_time = max_idle_time
        self.respect_robots = respect_robots  # <-- ADICIONADO
        self.proxy_manager = proxy_manager
        
        self.queue = Queue()
        self.visited: Set[str] = set()
        self.visited_lock = threading.Lock()
        self.urls: List[str] = []
        self.urls_lock = threading.Lock()
        self.paths: List[str] = []
        self.files: List[str] = []
        
        self.threads: List[threading.Thread] = []
        self.stop_event = threading.Event()
        self.status = CrawlerStatus.RUNNING
        self.interrupt_lock = threading.Lock()
        self.active_threads = 0
        self.active_threads_lock = threading.Lock()
        
        self.last_activity_time = time.time()
        self.activity_lock = threading.Lock()
        
        self.stats = CrawlerStats()
        self.stats_lock = threading.Lock()
        
        self.rate_limiter = RateLimiter(rate_limit)
        self.session = self._create_session(max_retries, user_agent)
        
        self.exclude_paths: Set[str] = set()
        self.allowed_extensions: Set[str] = {'.html', '.htm', '.php', '.asp', '.aspx', '.jsp', '.do', '.action'}
        self.exclude_extensions: Set[str] = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.mp4', '.mp3', '.css', '.js', '.ico'}
        
        self.protection_info = ProtectionInfo()
        
        self.robots_rules: Dict[str, List[str]] = {}
        self.disallowed_paths: Set[str] = set()
        
        self.logger = logging.getLogger(f"{__name__}.WebCrawler")
        self.partial_results_shown = False
        
        self._update_browser_headers()
    
    def _update_browser_headers(self):
        """Atualiza headers para simular um navegador real"""
        current_ua = self.session.headers.get('User-Agent', '')
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-GPC': '1',
            'Pragma': 'no-cache',
        }
        
        self.session.headers.update(headers)
        if current_ua:
            self.session.headers['User-Agent'] = current_ua
    
    def _create_session(self, max_retries: int, user_agent: str) -> requests.Session:
        session = requests.Session()
        
        adapter = CustomHTTPAdapter(max_retries=max_retries, pool_connections=20, pool_maxsize=20)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        if user_agent:
            session.headers.update({'User-Agent': user_agent})
        else:
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        
        # Configura proxy se disponível
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                session.proxies.update(proxy)
                self.logger.info(f"Using proxy: {self.proxy_manager.get_proxy_info()}")
        
        return session
    
    def get_status_color(self, status_code: int) -> str:
        """Retorna a cor para um status code"""
        if 200 <= status_code < 300:
            return "green"
        elif 300 <= status_code < 400:
            return "cyan"
        elif status_code == 400:
            return "yellow"
        elif status_code == 401:
            return "yellow"
        elif status_code == 403:
            return "red"
        elif status_code == 404:
            return "yellow"
        elif status_code == 429:
            return "red"
        elif 500 <= status_code < 600:
            return "red"
        else:
            return "white"
    
    def get_status_icon(self, status_code: int) -> str:
        """Retorna o ícone para um status code"""
        if 200 <= status_code < 300:
            return "✓"
        elif 300 <= status_code < 400:
            return "➡"
        elif status_code == 400:
            return "⚠"
        elif status_code == 401:
            return "🔒"
        elif status_code == 403:
            return "🚫"
        elif status_code == 404:
            return "❓"
        elif status_code == 429:
            return "🐌"
        elif 500 <= status_code < 600:
            return "💥"
        else:
            return "•"
    
    def log_request(self, url: str, status_code: int, message: str = ""):
        """Log de requisição com status code colorido"""
        color = self.get_status_color(status_code)
        icon = self.get_status_icon(status_code)
        
        # Cria mensagem formatada
        formatted_msg = f"[{color}]{icon} {status_code}[/{color}] {url}"
        if message:
            formatted_msg += f" - {message}"
        
        # Log com a mensagem formatada
        self.logger.info(formatted_msg)
    
    def detect_protection(self, response: requests.Response, url: str) -> ProtectionInfo:
        protection = ProtectionInfo()
        
        if response.status_code == 403:
            protection.type = ProtectionType.BLOCKED
            protection.details = f"Access forbidden (403)"
            protection.requires_cookie = True
            
            if 'cf-ray' in response.headers:
                protection.type = ProtectionType.CLOUDFLARE
                protection.details = "Cloudflare protection detected"
                protection.requires_js = True
                protection.challenge_page = True
                
            elif 'x-sucuri-id' in response.headers:
                protection.type = ProtectionType.SUCURI
                protection.details = "Sucuri protection detected"
                protection.requires_cookie = True
                
        elif response.status_code == 429:
            protection.type = ProtectionType.RATE_LIMITED
            protection.details = "Rate limited (429)"
        
        if response.text:
            html_lower = response.text.lower()
            
            if 'cloudflare' in html_lower and ('attention required' in html_lower or 'just a moment' in html_lower):
                protection.type = ProtectionType.CLOUDFLARE
                protection.details = "Cloudflare challenge page"
                protection.requires_js = True
                protection.challenge_page = True
                
            elif 'ddos-guard' in html_lower:
                protection.type = ProtectionType.DDOS_GUARD
                protection.details = "DDoS-Guard protection detected"
                protection.requires_js = True
                
            elif 'access denied' in html_lower or 'blocked' in html_lower:
                if protection.type == ProtectionType.NONE:
                    protection.type = ProtectionType.BLOCKED
                    protection.details = "Access denied page detected"
                    
            elif 'login' in html_lower and 'password' in html_lower and not protection.detected:
                protection.requires_cookie = True
                protection.details = "Login form detected - may require authentication"
        
        protection.detected = protection.type != ProtectionType.NONE
        return protection
    
    def get_common_paths(self) -> List[str]:
        """Retorna paths comuns para testar acessibilidade"""
        parsed = urlparse(self.original_base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        common_paths = [
            '', '/', '/index.html', '/index.php', '/index.asp', '/index.aspx',
            '/default.html', '/default.php', '/default.asp', '/default.aspx',
            '/home.html', '/home.php', '/main.html', '/main.php',
            '/wp-admin', '/admin', '/login', '/robots.txt', '/sitemap.xml',
        ]
        
        if parsed.path and parsed.path != '/':
            common_paths.insert(0, parsed.path)
            if '?' in parsed.path:
                base_path = parsed.path.split('?')[0]
                common_paths.insert(0, base_path)
        
        seen = set()
        unique_paths = []
        for path in common_paths:
            full_url = urljoin(base, path)
            if full_url not in seen:
                seen.add(full_url)
                unique_paths.append(full_url)
        
        return unique_paths
    
    def check_site_accessibility(self) -> bool:
        self.logger.info(f"Checking site accessibility: {self.base_url}")
        
        test_urls = self.get_common_paths()
        
        if self.base_url in test_urls:
            test_urls.remove(self.base_url)
        test_urls.insert(0, self.base_url)
        
        for test_url in test_urls:
            try:
                response = self.session.get(test_url, timeout=self.timeout, allow_redirects=True)
                
                # Log com status code colorido
                self.log_request(test_url, response.status_code)
                
                protection = self.detect_protection(response, test_url)
                
                if protection.detected:
                    self.logger.warning(f"Protection detected: {protection.details}")
                    
                    if protection.type == ProtectionType.CLOUDFLARE:
                        self.logger.warning("Cloudflare protection detected!")
                        self.logger.warning("Cookie may be expired or invalid")
                        
                    if response.status_code == 403:
                        continue
                
                if response.status_code == 200:
                    self.logger.info(f"Successfully accessed: {test_url}")
                    
                    if test_url != self.base_url:
                        self.logger.info(f"Using working URL: {test_url}")
                        self.base_url = test_url
                        self.queue = Queue()
                        self.visited.clear()
                    
                    return True
                    
            except requests.exceptions.ConnectionError:
                self.logger.debug(f"Connection error for {test_url}")
                continue
            except requests.exceptions.Timeout:
                self.logger.debug(f"Timeout for {test_url}")
                continue
            except Exception as e:
                self.logger.debug(f"Error testing {test_url}: {e}")
                continue
        
        self.logger.error("No accessible URLs found")
        return False
    
    def load_user_agents(self, file_path: str):
        try:
            with open(file_path, 'r') as f:
                agents = [line.strip() for line in f if line.strip()]
                if agents:
                    random_agent = random.choice(agents)
                    self.session.headers['User-Agent'] = random_agent
                    self.logger.info(f"Loaded {len(agents)} user agents")
        except Exception as e:
            self.logger.error(f"Error loading user agents: {e}")
    
    def load_robots_txt(self):
        try:
            robots_url = urljoin(self.base_url, '/robots.txt')
            response = self.session.get(robots_url, timeout=5)
            
            if response.status_code == 200:
                current_agent = None
                for line in response.text.split('\n'):
                    line = line.strip().lower()
                    if line.startswith('user-agent:'):
                        current_agent = line.split(':', 1)[1].strip()
                        if current_agent not in self.robots_rules:
                            self.robots_rules[current_agent] = []
                    elif line.startswith('disallow:') and current_agent:
                        path = line.split(':', 1)[1].strip()
                        if path:
                            self.robots_rules[current_agent].append(path)
                            if current_agent == '*' or current_agent == 'silkcrawler':
                                self.disallowed_paths.add(path)
                
                self.logger.info(f"Loaded robots.txt with {len(self.robots_rules)} user-agent rules")
        except Exception as e:
            self.logger.warning(f"Could not load robots.txt: {e}")
    
    def update_activity(self):
        with self.activity_lock:
            self.last_activity_time = time.time()
    
    def check_idle_timeout(self) -> bool:
        with self.activity_lock:
            idle_time = time.time() - self.last_activity_time
            if idle_time > self.max_idle_time and self.queue.empty():
                self.logger.warning(f"No activity for {idle_time:.0f} seconds, stopping crawler")
                return True
        return False
    
    def is_allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            parsed = urlparse(url)
            path = parsed.path
            
            for disallowed in self.disallowed_paths:
                if disallowed and path.startswith(disallowed):
                    with self.stats_lock:
                        self.stats.blocked_by_robots += 1
                    break
            return True
        
        parsed = urlparse(url)
        path = parsed.path
        rules = self.robots_rules.get('*', [])
        
        for rule in rules:
            if rule and path.startswith(rule):
                return False
        return True
    
    def normalize_url(self, base: str, link: str) -> Optional[str]:
        try:
            if link.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:')):
                return None
            
            full_url = urljoin(base, link)
            full_url = urldefrag(full_url)[0]
            
            parsed = urlparse(full_url)
            
            if parsed.scheme not in ['http', 'https']:
                return None
            
            if not parsed.netloc.endswith(self.domain_base) and self.domain_base not in parsed.netloc:
                return None
            
            return full_url
        except Exception as e:
            self.logger.debug(f"Error normalizing URL {link}: {e}")
            return None
    
    def extract_links(self, html: str, base_url: str) -> List[str]:
        links = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if href:
                    normalized = self.normalize_url(base_url, href)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for form in soup.find_all('form', action=True):
                action = form['action'].strip()
                if action:
                    normalized = self.normalize_url(base_url, action)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for frame in soup.find_all(['iframe', 'frame'], src=True):
                src = frame['src'].strip()
                if src:
                    normalized = self.normalize_url(base_url, src)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for link in soup.find_all('link', href=True):
                href = link['href'].strip()
                if href:
                    normalized = self.normalize_url(base_url, href)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for script in soup.find_all('script', src=True):
                src = script['src'].strip()
                if src:
                    normalized = self.normalize_url(base_url, src)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for img in soup.find_all('img', src=True):
                src = img['src'].strip()
                if src:
                    normalized = self.normalize_url(base_url, src)
                    if normalized and normalized not in links:
                        links.append(normalized)
            
            for meta in soup.find_all('meta', attrs={'http-equiv': 'refresh'}):
                content = meta.get('content', '')
                if 'url=' in content.lower():
                    url_match = re.search(r'url=([^;]+)', content, re.IGNORECASE)
                    if url_match:
                        refresh_url = url_match.group(1).strip()
                        normalized = self.normalize_url(base_url, refresh_url)
                        if normalized and normalized not in links:
                            links.append(normalized)
                    
        except Exception as e:
            self.logger.error(f"Error extracting links from {base_url}: {e}")
        
        return links
    
    def classify_url(self, url: str) -> Tuple[bool, str]:
        parsed = urlparse(url)
        path = Path(parsed.path)
        extension = path.suffix.lower()
        
        if extension:
            if extension in self.exclude_extensions:
                return False, 'excluded'
            return True, 'file'
        return True, 'path'
    
    def add_to_visited(self, url: str) -> bool:
        with self.visited_lock:
            if url in self.visited:
                return False
            self.visited.add(url)
            return True
    
    def worker(self):
        thread_name = threading.current_thread().name
        
        with self.active_threads_lock:
            self.active_threads += 1
        
        self.logger.debug(f"Thread {thread_name} started (active: {self.active_threads})")
        
        while not self.stop_event.is_set():
            try:
                url, depth = self.queue.get(timeout=2)
                self.update_activity()
            except Empty:
                if self.queue.empty():
                    with self.active_threads_lock:
                        if self.active_threads <= 1:
                            break
                continue
            
            if self.stop_event.is_set():
                self.queue.task_done()
                break
            
            if depth > self.max_depth:
                self.queue.task_done()
                continue
            
            if not self.add_to_visited(url):
                self.queue.task_done()
                continue
            
            self.is_allowed_by_robots(url)
            
            parsed = urlparse(url)
            if parsed.path in self.exclude_paths:
                self.queue.task_done()
                continue
            
            response = self.test_url(url)
            if not response:
                self.queue.task_done()
                continue
            
            is_resource, url_type = self.classify_url(url)
            if is_resource:
                if url_type == 'file':
                    with self.urls_lock:
                        if url not in self.urls:
                            self.files.append(parsed.path)
                            with self.stats_lock:
                                self.stats.total_files += 1
                else:
                    with self.urls_lock:
                        if url not in self.urls:
                            self.paths.append(parsed.path)
                            with self.stats_lock:
                                self.stats.total_paths += 1
                
                with self.urls_lock:
                    if url not in self.urls:
                        self.urls.append(url)
                        with self.stats_lock:
                            self.stats.total_urls += 1
                            self.stats.unique_urls = len(self.visited)
            
            try:
                html = response.text
                links = self.extract_links(html, url)
                
                robots_indicator = " [ROBOTS.TXT BLOCKED]" if any(parsed.path.startswith(disallowed) for disallowed in self.disallowed_paths) else ""
                
                # Log com status code colorido
                self.log_request(url, response.status_code, f"depth {depth} - Found {len(links)} links{robots_indicator}")
                
                for link in links:
                    if not self.stop_event.is_set():
                        self.queue.put((link, depth + 1))
                        self.update_activity()
                
                for parent_url in self.get_directory_chain(url):
                    if not self.stop_event.is_set():
                        self.queue.put((parent_url, depth + 1))
                        self.update_activity()
                        
            except Exception as e:
                self.logger.error(f"Error processing {url}: {e}")
            
            self.queue.task_done()
        
        with self.active_threads_lock:
            self.active_threads -= 1
        
        self.logger.debug(f"Thread {thread_name} finished (active: {self.active_threads})")
    
    def get_directory_chain(self, url: str) -> List[str]:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        urls = []
        
        for i in range(len(parts), 0, -1):
            path = '/' + '/'.join(parts[:i]) + '/'
            full_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            urls.append(full_url)
        
        return urls
    
    def test_url(self, url: str) -> Optional[requests.Response]:
        if self.stop_event.is_set():
            return None
            
        try:
            self.rate_limiter.wait()
            
            with self.stats_lock:
                self.stats.total_requests += 1
            
            # Se tiver proxy rotativo, atualiza a cada requisição
            if self.proxy_manager and self.proxy_manager.rotate_proxy:
                new_proxy = self.proxy_manager.get_proxy()
                if new_proxy:
                    self.session.proxies.update(new_proxy)
            
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            
            # Atualiza estatísticas de status code
            with self.stats_lock:
                self.stats.status_codes[response.status_code] = self.stats.status_codes.get(response.status_code, 0) + 1
                
                if response.status_code == 200:
                    self.stats.successful_requests += 1
                else:
                    self.stats.failed_requests += 1
            
            return response if response.status_code == 200 else None
            
        except requests.exceptions.Timeout:
            self.logger.debug(f"Timeout for URL: {url}")
            with self.stats_lock:
                self.stats.failed_requests += 1
            return None
        except requests.exceptions.ConnectionError:
            self.logger.debug(f"Connection error for URL: {url}")
            with self.stats_lock:
                self.stats.failed_requests += 1
            return None
        except requests.exceptions.ProxyError as e:
            self.logger.error(f"Proxy error for {url}: {e}")
            with self.stats_lock:
                self.stats.failed_requests += 1
            return None
        except Exception as e:
            self.logger.debug(f"Unexpected error for URL {url}: {e}")
            with self.stats_lock:
                self.stats.failed_requests += 1
            return None
    
    def start(self):
        if not self.check_site_accessibility():
            self.logger.error("Site is not accessible or blocked")
            self.status = CrawlerStatus.ERROR
            return
        
        self.logger.info(f"Starting crawler on {self.base_url}")
        self.logger.warning("robots.txt will be IGNORED - crawling all paths including disallowed ones")
        
        self.load_robots_txt()
        
        self.queue.put((self.base_url, 0))
        self.update_activity()
        
        for i in range(self.max_threads):
            thread = threading.Thread(target=self.worker, name=f"Crawler-{i+1}")
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
        
        try:
            while not self.stop_event.is_set():
                if self.check_idle_timeout():
                    self.stop_event.set()
                    break
                
                if self.queue.empty():
                    with self.active_threads_lock:
                        if self.active_threads == 0:
                            self.logger.info("All URLs processed, crawler finished")
                            self.status = CrawlerStatus.COMPLETED
                            break
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            self.interrupt()
        finally:
            self.stop()
    
    def interrupt(self):
        with self.interrupt_lock:
            if self.status in [CrawlerStatus.INTERRUPTED, CrawlerStatus.STOPPED]:
                return
            
            self.logger.warning("\nKeyboardInterrupt detected! Stopping crawler gracefully...")
            self.status = CrawlerStatus.INTERRUPTED
            self.stop_event.set()
            
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except Empty:
                    break
            
            for thread in self.threads:
                thread.join(timeout=3)
            
            self.stats.end_time = datetime.now()
            self.logger.info("Crawler interrupted by user.")
    
    def stop(self):
        if self.status in [CrawlerStatus.STOPPED, CrawlerStatus.INTERRUPTED, CrawlerStatus.COMPLETED]:
            return
            
        self.logger.info("Stopping crawler...")
        self.stop_event.set()
        
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except Empty:
                break
        
        for thread in self.threads:
            thread.join(timeout=5)
        
        if not self.stats.end_time:
            self.stats.end_time = datetime.now()
        
        if self.status != CrawlerStatus.INTERRUPTED:
            self.status = CrawlerStatus.STOPPED
        
        self.logger.info(f"Crawler stopped. Stats: {self.get_stats_summary()}")
    
    def get_stats_summary(self) -> str:
        return (f"URLs: {self.stats.total_urls} unique, "
                f"Requests: {self.stats.total_requests} ({self.stats.success_rate:.1f}% success), "
                f"Files: {self.stats.total_files}, Paths: {self.stats.total_paths}, "
                f"Blocked by robots.txt: {self.stats.blocked_by_robots}, "
                f"Duration: {self.stats.duration:.2f}s")
    
    def print_stats(self, is_partial: bool = False):
        console = Console()
        
        title = "Partial Results - Crawler Statistics" if is_partial else "Crawler Statistics"
        title_style = "bold yellow" if is_partial else "bold blue"
        
        table = Table(title=title, title_style=title_style)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Unique URLs", str(self.stats.unique_urls))
        table.add_row("Total Requests", str(self.stats.total_requests))
        table.add_row("Successful Requests (200)", str(self.stats.successful_requests))
        table.add_row("Failed Requests", str(self.stats.failed_requests))
        table.add_row("Success Rate", f"{self.stats.success_rate:.1f}%")
        table.add_row("Files Found", str(self.stats.total_files))
        table.add_row("Paths Found", str(self.stats.total_paths))
        table.add_row("Blocked by robots.txt (Crawled)", str(self.stats.blocked_by_robots))
        table.add_row("Duration", f"{self.stats.duration:.2f} seconds")
        
        if self.stats.duration > 0 and self.stats.unique_urls > 0:
            table.add_row("Average Speed", f"{self.stats.unique_urls / self.stats.duration:.2f} URLs/sec")
        
        # Informações do proxy
        if self.proxy_manager:
            table.add_row("Proxy", self.proxy_manager.get_proxy_info())
        
        # Adiciona tabela de status codes
        if self.stats.status_codes:
            status_table = Table(title="Status Code Distribution", title_style="cyan")
            status_table.add_column("Status Code", style="bold")
            status_table.add_column("Count", style="green")
            status_table.add_column("Percentage", style="yellow")
            
            total = sum(self.stats.status_codes.values())
            for code, count in sorted(self.stats.status_codes.items()):
                color = self.get_status_color(code)
                icon = self.get_status_icon(code)
                percentage = (count / total) * 100
                status_table.add_row(
                    f"[{color}]{icon} {code}[/{color}]",
                    str(count),
                    f"{percentage:.1f}%"
                )
            
            console.print(status_table)
        
        console.print(table)
        
        if self.protection_info.detected:
            console.print(Panel(
                f"[red]⚠️  Protection Detected: {self.protection_info.details}[/red]\n"
                f"[yellow]• Type: {self.protection_info.type.value}[/yellow]\n"
                f"[yellow]• Requires JS: {self.protection_info.requires_js}[/yellow]\n"
                f"[yellow]• Requires Cookies: {self.protection_info.requires_cookie}[/yellow]\n"
                f"[cyan]💡 Solutions:[/cyan]\n"
                f"  1. Get a fresh cookie from browser\n"
                f"  2. Use headless browser (Selenium, Playwright)\n"
                f"  3. Reduce request rate: -rl 1 -t 1\n"
                f"  4. Use proxies: --proxy-list proxy.txt\n"
                f"  5. Wait and retry: Cloudflare cookies expire after ~30min",
                title="Site Protection Notice",
                border_style="red"
            ))
    
    def build_url_tree(self) -> Dict:
        root = {}
        for url in self.urls:
            parsed = urlparse(url)
            parts = [p for p in parsed.path.strip('/').split('/') if p]
            current = root
            for part in parts:
                current = current.setdefault(part, {})
        return root
    
    def render_tree(self, tree_dict: Dict, rich_tree: Tree, highlight_robots: bool = True):
        for key, subtree in sorted(tree_dict.items()):
            is_disallowed = any(f"/{key}" in disallowed or key in disallowed for disallowed in self.disallowed_paths)
            
            if subtree:
                if is_disallowed and highlight_robots:
                    branch = rich_tree.add(f"[red]🚫 {key}/ [dim](blocked by robots.txt)[/dim][/red]")
                else:
                    branch = rich_tree.add(f"[green]{key}/")
                self.render_tree(subtree, branch, highlight_robots)
            else:
                if is_disallowed and highlight_robots:
                    rich_tree.add(f"[red]🚫 {key}[/red] [dim](blocked by robots.txt)[/dim]")
                else:
                    rich_tree.add(f"[yellow]{key}[/yellow]")
    
    def print_tree(self, is_partial: bool = False):
        console = Console()
        
        if is_partial:
            print("\n[bold yellow]Partial Site Structure (Sitemap):[/bold yellow]\n")
        else:
            print("\n[bold blue]Site Structure (Sitemap):[/bold blue]\n")
        
        if not self.urls:
            print("[dim]No URLs discovered yet.[/dim]")
            return
            
        tree_data = self.build_url_tree()
        root_tree = Tree(f"[bold white]{self.domain_base}/[/bold white]")
        self.render_tree(tree_data, root_tree)
        console.print(root_tree)
        
        print("\n[dim]Legend:[/dim]")
        print("[green]📁 Directory[/green]")
        print("[yellow]📄 File[/yellow]")
        print("[red]🚫 Path blocked by robots.txt (but crawled anyway)[/red]")
    
    def show_partial_results(self):
        console = Console()
        
        if self.partial_results_shown:
            return
        self.partial_results_shown = True
        
        console.print("\n[bold yellow]⚠️  Crawler Interrupted - Showing Partial Results[/bold yellow]\n")
        self.print_stats(is_partial=True)
        self.print_tree(is_partial=True)

def signal_handler(signum, frame):
    raise KeyboardInterrupt()

def print_logo():
    console = Console()
    logo = """[bold blue]
    ╔════════════════════════════════════════════╗
    ║               🕷  SILKPATH PRO 🕸              ║
    ║  Advanced web crawler for reconnaissance   ║
    ╚════════════════════════════════════════════╝[/bold blue]

           [white]\\     .--.
            \\   |o_o |     [grey]Spinning through the web...[/grey]
                |:_/ |     [grey]Discovering hidden paths.[/grey]
               //   \\ \\
              (|     | )
             /'\\_   _/`\\
             \\___)=(___/

[bold white]  Author:[/] Wesley Ruan
[bold white]  Version:[/] 2.0 (Improved Edition)
[bold white]  Desc  :[/] Advanced multi-threaded web crawler with proxy support
[bold blue]----------------------------------------------------------[/bold blue]
"""
    console.print(logo)

def parse_proxy_list(proxy_string: str) -> List[str]:
    """Parseia string de proxies no formato ip:port,ip:port ou arquivo:path"""
    if proxy_string.startswith('file:'):
        # Carrega de arquivo
        file_path = proxy_string[5:]
        try:
            with open(file_path, 'r') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            logger.error(f"Error loading proxy file: {e}")
            return []
    else:
        # Lista separada por vírgula
        return [p.strip() for p in proxy_string.split(',') if p.strip()]

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print_logo()
    
    parser = argparse.ArgumentParser(
        description="Advanced web crawler with multi-threading and tree visualization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic crawl
  %(prog)s -u https://example.com
  
  # With cookies (Cloudflare bypass)
  %(prog)s -u https://example.com -c "cf_clearance=YOUR_COOKIE"
  
  # With single proxy
  %(prog)s -u https://example.com --proxy "http://127.0.0.1:8080"
  
  # With multiple proxies (rotating)
  %(prog)s -u https://example.com --proxy-list "http://proxy1:8080,http://proxy2:8080" --rotate-proxy
  
  # With proxy list from file
  %(prog)s -u https://example.com --proxy-list "file:proxies.txt" --rotate-proxy
  
  # With authenticated proxy
  %(prog)s -u https://example.com --proxy "http://user:pass@proxy.com:8080"
  
  # With random user agents and rate limiting
  %(prog)s -u https://example.com --random-agent -rl 2 -t 3
  
  # Save results to file
  %(prog)s -u https://example.com -o results.txt
        """
    )
    
    parser.add_argument("-u", "--url", required=True, help="Base URL to crawl")
    parser.add_argument("-t", "--threads", type=int, default=5, help="Number of threads (default: 5)")
    parser.add_argument("-d", "--depth", type=int, default=3, help="Maximum crawl depth (default: 3)")
    parser.add_argument("-c", "--cookie", help="Cookie string (format: key=value;...)")
    parser.add_argument("-ep", "--exclude-paths", nargs='*', help="Paths to exclude from crawling")
    parser.add_argument("-a", "--user-agent", help="Custom user agent string")
    parser.add_argument("-ra", "--random-agent", action="store_true", help="Use random user agents")
    parser.add_argument("-ua-file", "--user-agent-file", help="File containing user agents (one per line)")
    parser.add_argument("-rl", "--rate-limit", type=float, default=3, help="Requests per second limit (default: 3)")
    parser.add_argument("-to", "--timeout", type=int, default=15, help="Request timeout in seconds (default: 15)")
    parser.add_argument("-rt", "--retries", type=int, default=3, help="Number of retries for failed requests (default: 3)")
    parser.add_argument("-idle", "--idle-timeout", type=int, default=30, help="Idle timeout in seconds (default: 30)")
    parser.add_argument("-o", "--output", help="Output file to save results")
    
    # Proxy arguments
    parser.add_argument("-p", "--proxy", help="Single proxy URL (format: http://ip:port or http://user:pass@ip:port)")
    parser.add_argument("-pl", "--proxy-list", help="Proxy list (comma-separated or file:path) - supports rotation")
    parser.add_argument("-rp", "--rotate-proxy", action="store_true", help="Rotate proxies for each request (requires --proxy-list)")
    parser.add_argument("-pa", "--proxy-auth", help="Proxy authentication (format: user:pass) - applies to all proxies")
    
    parser.add_argument("--version", action="version", version="%(prog)s 2.0")
    
    args = parser.parse_args()
    
    # Configura proxy manager
    proxy_manager = None
    if args.proxy:
        # Proxy único
        proxy_manager = ProxyManager(proxy_list=[args.proxy], rotate_proxy=False, proxy_auth=args.proxy_auth)
    elif args.proxy_list:
        # Lista de proxies
        proxy_list = parse_proxy_list(args.proxy_list)
        if proxy_list:
            proxy_manager = ProxyManager(proxy_list=proxy_list, rotate_proxy=args.rotate_proxy, proxy_auth=args.proxy_auth)
        else:
            logger.error("No valid proxies found in proxy list")
            sys.exit(1)
    
    crawler = WebCrawler(
        base_url=args.url,
        max_depth=args.depth,
        max_threads=args.threads,
        timeout=args.timeout,
        max_retries=args.retries,
        rate_limit=args.rate_limit,
        respect_robots=False,
        user_agent=args.user_agent,
        max_idle_time=args.idle_timeout,
        proxy_manager=proxy_manager
    )
    
    if args.exclude_paths:
        crawler.exclude_paths = set(args.exclude_paths)
    
    if args.cookie:
        crawler.session.headers.update({'Cookie': args.cookie})
        logger.info("Cookie added to session")
    
    if args.random_agent:
        if args.user_agent_file:
            crawler.load_user_agents(args.user_agent_file)
        else:
            default_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            ]
            random_agent = random.choice(default_agents)
            crawler.session.headers['User-Agent'] = random_agent
            logger.info(f"Using random user agent: {random_agent[:80]}...")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=Console()
        ) as progress:
            task = progress.add_task("[cyan]Crawling...", total=None)
            
            def update_progress():
                last_count = 0
                last_queue = 0
                while crawler.status == CrawlerStatus.RUNNING:
                    current = crawler.stats.unique_urls
                    queue_size = crawler.queue.qsize()
                    if current != last_count or queue_size != last_queue:
                        progress.update(task, description=f"[cyan]Crawling... (URLs: {current}, Queue: {queue_size}, Active: {crawler.active_threads})")
                        last_count = current
                        last_queue = queue_size
                    time.sleep(0.5)
            
            progress_thread = threading.Thread(target=update_progress, daemon=True)
            progress_thread.start()
            
            crawler.start()
        
        if crawler.status == CrawlerStatus.INTERRUPTED:
            crawler.show_partial_results()
        elif crawler.status == CrawlerStatus.COMPLETED:
            print("\n[bold green]✓ Crawler completed successfully![/bold green]\n")
            crawler.print_stats(is_partial=False)
            crawler.print_tree(is_partial=False)
        elif crawler.status == CrawlerStatus.ERROR:
            print("\n[bold red]✗ Crawler encountered an error![/bold red]\n")
            print("[red]The site appears to be protected by Cloudflare or similar service.[/red]")
            print("\n[bold yellow]Troubleshooting tips:[/bold yellow]")
            print("1. Get a fresh cf_clearance cookie:")
            print("   - Open browser and visit the site")
            print("   - Solve the Cloudflare challenge (if any)")
            print("   - Open DevTools (F12) > Application > Cookies")
            print("   - Copy the value of 'cf_clearance'")
            print(f"   - Run: python SilkPath.py -u {args.url} -c \"cf_clearance=YOUR_COOKIE\"")
            print("\n2. Use a headless browser solution like Selenium or Playwright")
            print("3. Use proxies to avoid IP blocking:")
            print(f"   python SilkPath.py -u {args.url} --proxy-list \"file:proxies.txt\" --rotate-proxy")
            print("4. Reduce threads and rate limit:")
            print(f"   python SilkPath.py -u {args.url} -t 1 -rl 1")
        else:
            print("\n")
            crawler.print_stats(is_partial=False)
            crawler.print_tree(is_partial=False)
        
        if args.output and (crawler.urls or crawler.files or crawler.paths):
            try:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write("=== Crawler Results ===\n\n")
                    f.write(f"Base URL: {args.url}\n")
                    f.write(f"Depth: {args.depth}\n")
                    f.write(f"Threads: {args.threads}\n")
                    f.write(f"Status: {crawler.status.value}\n")
                    
                    if proxy_manager:
                        f.write(f"Proxy: {proxy_manager.get_proxy_info()}\n")
                    f.write("\n")
                    
                    if crawler.protection_info.detected:
                        f.write("=== Protection Detected ===\n")
                        f.write(f"Type: {crawler.protection_info.type.value}\n")
                        f.write(f"Details: {crawler.protection_info.details}\n\n")
                    
                    f.write("=== URLs Found ===\n")
                    for url in crawler.urls:
                        f.write(f"{url}\n")
                    
                    f.write("\n=== Files Found ===\n")
                    for file in crawler.files:
                        f.write(f"{file}\n")
                    
                    f.write("\n=== Paths Found ===\n")
                    for path in crawler.paths:
                        f.write(f"{path}\n")
                    
                    f.write("\n=== Statistics ===\n")
                    f.write(f"Total URLs: {crawler.stats.total_urls}\n")
                    f.write(f"Unique URLs: {crawler.stats.unique_urls}\n")
                    f.write(f"Files: {crawler.stats.total_files}\n")
                    f.write(f"Paths: {crawler.stats.total_paths}\n")
                    f.write(f"Duration: {crawler.stats.duration:.2f} seconds\n")
                    f.write(f"Success Rate: {crawler.stats.success_rate:.1f}%\n")
                    
                    f.write("\n=== Status Code Distribution ===\n")
                    for code, count in sorted(crawler.stats.status_codes.items()):
                        f.write(f"{code}: {count}\n")
                
                logger.info(f"Results saved to {args.output}")
            except Exception as e:
                logger.error(f"Error saving results: {e}")
        
    except KeyboardInterrupt:
        print("\n[bold red]! Emergency interrupt detected![/bold red]")
        if crawler:
            crawler.show_partial_results()
        return 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
