# 🕷️ SilkPath - Advanced Web Crawler

[![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0-red.svg)](https://github.com/yourusername/silkpath)

> **SilkPath** é um crawler web avançado e multithreaded projetado para mapeamento de estruturas de sites, descoberta de caminhos ocultos e análise de aplicações web. Desenvolvido para profissionais de segurança, desenvolvedores e entusiastas de reconhecimento web.

![SilkPath Banner](https://via.placeholder.com/800x200/0a0e27/ffffff?text=SilkPath+Web+Crawler)

## ✨ Características Principais

- 🚀 **Multithreading Avançado** - Crawling paralelo com controle de threads
- 🌳 **Visualização em Árvore** - Estrutura hierárquica do site
- 🎯 **Reconhecimento Inteligente** - Detecção automática de arquivos e diretórios
- 🤖 **Respeito a Robots.txt** - Conformidade com padrões web
- ⚡ **Rate Limiting** - Controle de requisições por segundo
- 📊 **Estatísticas Detalhadas** - Métricas em tempo real
- 🔄 **Retry Automático** - Backoff exponencial para falhas
- 📝 **Logging Completo** - Registro detalhado de atividades
- 🎨 **Interface Rica** - Visualização colorida com `rich`

## 📋 Pré-requisitos

- Python 3.7 ou superior
- Pip (gerenciador de pacotes Python)

## 🔧 Instalação

### Clonando o Repositório

```bash
git clone https://github.com/wesleyruam/silkpath.git
cd silkpath
```

### Instalando Dependências

```bash
pip install -r requirements.txt
```

### Dependências Principais

```txt
requests>=2.28.0
beautifulsoup4>=4.11.0
rich>=13.0.0
urllib3>=1.26.0
```

## 🚀 Uso Básico

### Comando Simples

```bash
python silkpath.py -u https://exemplo.com
```

### Exemplos Avançados

```bash
# Crawler com 20 threads e profundidade 5
python silkpath.py -u https://exemplo.com -t 20 -d 5

# Com rate limiting e user agent aleatório
python silkpath.py -u https://exemplo.com --random-agent --rate-limit 5

# Ignorando robots.txt e excluindo caminhos específicos
python silkpath.py -u https://exemplo.com --no-robots -ep /admin /login

# Com cookie de autenticação
python silkpath.py -u https://exemplo.com -c "sessionid=abc123; token=xyz789"

# Salvando resultados em arquivo
python silkpath.py -u https://exemplo.com -o resultados.txt

# User agent personalizado
python silkpath.py -u https://exemplo.com -a "Mozilla/5.0 (Custom Bot)"
```

## 📖 Argumentos da Linha de Comando

| Argumento | Descrição | Padrão | Exemplo |
|-----------|-----------|--------|---------|
| `-u, --url` | URL base para crawler | **Obrigatório** | `-u https://exemplo.com` |
| `-t, --threads` | Número de threads | 10 | `-t 20` |
| `-d, --depth` | Profundidade máxima de crawling | 3 | `-d 5` |
| `-c, --cookie` | Cookie para autenticação | - | `-c "key=value"` |
| `-ep, --exclude-paths` | Caminhos para excluir | - | `-ep /admin /backup` |
| `-a, --user-agent` | User agent personalizado | - | `-a "MyBot/1.0"` |
| `-ra, --random-agent` | User agent aleatório | False | `--random-agent` |
| `-ua-file, --user-agent-file` | Arquivo com user agents | - | `-ua-file agents.txt` |
| `-rl, --rate-limit` | Limite de req/segundo | 10 | `-rl 5` |
| `-to, --timeout` | Timeout em segundos | 10 | `-to 15` |
| `-rt, --retries` | Número de tentativas | 3 | `-rt 5` |
| `-nr, --no-robots` | Ignorar robots.txt | False | `--no-robots` |
| `-o, --output` | Arquivo de saída | - | `-o resultados.txt` |
| `--version` | Mostrar versão | - | `--version` |

## 📊 Exemplo de Saída

### Console com Visualização Rica

```
╔════════════════════════════════════════════╗
║               🕷  SILKPATH PRO 🕸              ║
║  Advanced web crawler for reconnaissance   ║
╚════════════════════════════════════════════╝

Crawling... (URLs: 127) ████████████████████ 100%

=== Crawler Statistics ===
┌─────────────────────────┬──────────────────┐
│ Metric                  │ Value            │
├─────────────────────────┼──────────────────┤
│ Total Unique URLs       │ 127              │
│ Total Requests          │ 145              │
│ Successful Requests     │ 127              │
│ Failed Requests         │ 18               │
│ Success Rate            │ 87.6%            │
│ Files Found             │ 23               │
│ Paths Found             │ 104              │
│ Duration                │ 12.34 seconds    │
│ Average Speed           │ 10.29 URLs/sec   │
└─────────────────────────┴──────────────────┘

Site Structure (Sitemap):

exemplo.com/
├── api/
│   ├── v1/
│   │   ├── users/
│   │   └── products/
│   └── v2/
├── assets/
│   ├── css/
│   ├── js/
│   └── images/
├── admin/
│   ├── login/
│   └── dashboard/
└── downloads/
    └── latest.zip

[✓] Scan completed successfully.
```

## 🏗️ Arquitetura

```
SilkPath/
├── silkpath.py          # Script principal
├── requirements.txt     # Dependências
├── README.md           # Documentação
├── LICENSE             # Licença
├── user-agents.txt     # Lista de user agents (opcional)
└── crawler.log         # Log de atividades (gerado)
```

## 🔒 Recursos de Segurança

### Rate Limiting
Controle inteligente de requisições por segundo para evitar sobrecarga do servidor alvo.

### Timeouts Configuráveis
Prevenção contra travamentos com timeouts ajustáveis para requisições.

## 📈 Performance

### Benchmarks (em ambiente controlado)

| Configuração | URLs/segundo | Tempo médio |
|--------------|--------------|-------------|
| 5 threads, depth 3 | 8-12 | 30s |
| 10 threads, depth 3 | 15-20 | 20s |
| 20 threads, depth 5 | 25-35 | 45s |
| 50 threads, depth 3 | 40-50 | 15s |

*Nota: Performance pode variar conforme rede, servidor alvo e configurações.*

## 🛠️ Personalização

### Adicionando User Agents Personalizados

Crie um arquivo `user-agents.txt` com um user agent por linha:

```txt
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36
```

### Configuração de Exclusões

Exclua caminhos específicos do crawling:

```bash
python silkpath.py -u https://exemplo.com -ep /logout /delete /private
```

## 🐛 Troubleshooting

### Problemas Comuns

**Q: O crawler não está encontrando links?**
- Verifique se a URL base está correta
- Aumente a profundidade com `-d`
- Verifique se o site usa JavaScript (o SilkPath não executa JS)

**Q: Muitas requisições falhando?**
- Reduza o número de threads com `-t`
- Aumente o timeout com `-to`
- Adicione rate limiting com `-rl`

**Q: Erro de conexão?**
- Verifique sua conexão de internet
- Confirme se a URL está acessível
- Verifique se há firewall bloqueando

**Q: O crawler está muito lento?**
- Aumente o número de threads
- Aumente o rate limit
- Verifique se há muitos timeouts

## 📝 Logging

O SilkPath gera logs detalhados em dois locais:

1. **Console**: Logs em tempo real com níveis de severidade
2. **Arquivo**: `crawler.log` com histórico completo

### Níveis de Log

- `INFO`: Atividades normais do crawler
- `DEBUG`: Informações detalhadas para debugging
- `WARNING`: Avisos sobre comportamentos inesperados
- `ERROR`: Erros recuperáveis
- `CRITICAL`: Erros fatais

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

## 👥 Autores

- **Wesley Ruan** - *Trabalho inicial* - [@yourusername](https://github.com/wesleyruam)

## ⚠️ Aviso Legal

**SilkPath é uma ferramenta de reconhecimento para fins educacionais e de segurança autorizada.**

- 🛡️ Use apenas em sites que você possui autorização para testar
- 🚫 Não use para atividades maliciosas ou não autorizadas
- ⚖️ Respeite as leis locais e os termos de serviço dos sites
- 🤝 Sempre respeite robots.txt e as políticas do site

O uso indevido desta ferramenta é de total responsabilidade do usuário.

## 🔄 Roadmap

### Versão 2.0 (Atual)
- ✅ Multithreading avançado
- ✅ Visualização em árvore
- ✅ Rate limiting
- ✅ Logging completo

### Versão 2.1 (Planejado)
- 🔄 Suporte a JavaScript (headless browser)
- 🔄 Exportação em múltiplos formatos (JSON, XML)
- 🔄 Filtros avançados
- 🔄 Interface web básica

### Versão 3.0 (Futuro)
- 🚀 Crawling distribuído
- 🚀 Análise de vulnerabilidades
- 🚀 Integração com ferramentas de segurança
- 🚀 API RESTful

---

**Feito com 🕷️ por Wesley Ruan**
