---

### 🕷️ SILKPATH — Multithreaded Web Crawler for Reconnaissance

**SILKPATH** é um crawler multithread em Python projetado para exploração e mapeamento de sites durante atividades de reconhecimento. Ele percorre recursivamente páginas web, constrói um sitemap visual da estrutura de diretórios e identifica arquivos e caminhos ocultos, tudo com suporte a cookies, múltiplos *User-Agents*, exclusão de rotas e profundidade de busca configurável.

#### 🔍 Funcionalidades:

* 🌐 Rastreamento recursivo a partir de uma URL base
* 🧵 Suporte a múltiplas threads para maior desempenho
* 🍪 Suporte a cookies personalizados
* 🦡 Suporte a User-Agent fixo ou aleatório (via arquivo)
* 📂 Mapeamento de diretórios e arquivos acessados
* 🌲 Geração de estrutura visual do site com Rich (Sitemap)
* 🚫 Exclusão de rotas específicas (`--exclude_paths`)
* 🛡️ Útil em fases de *recon* para pentest e bug bounty

#### 🛠️ Exemplo de uso:

```bash
python silkpath.py -u https://example.com -t 20 -ra --exclude_paths /logout /admin
```

#### 📁 Requisitos:

* Python 3.13+
* `requests`, `beautifulsoup4`, `rich`

Instale com:

```bash
pip install -r requirements.txt
```

#### ✒️ Autor:

**Wesley Ruan**
GitHub: [@wesleyruam](https://github.com/wesleyruam)

---
