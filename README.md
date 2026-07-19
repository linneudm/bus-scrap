# Bus Scrap

Monitoramento de passagens de ônibus no Brasil. Consulta FlixBus, ClickBus e QueroPassagem, agenda buscas diárias e envia o resultado por e-mail HTML.

## Funcionalidades

- Busca única via CLI (`python -m bus_scrap`)
- Serviço agendado diário (padrão: **10:00**, fuso `America/Sao_Paulo`)
- Parâmetros configuráveis em runtime pelo terminal (`email`, `origem`, `destino`, `data`, etc.)
- Template de e-mail HTML com CSS
- Logs formatados no console e em `data/log.txt`
- Pronto para produção com Docker / Docker Compose

## Providers

| Site              | Observação                                                               |
| ----------------- | ------------------------------------------------------------------------ |
| **QueroPassagem** | Em geral o mais completo para rotas regionais                            |
| **ClickBus**      | Usa Playwright (Chromium) por causa de anti-bot                          |
| **FlixBus**       | Depende de cobertura da rota; algumas cidades podem não retornar ofertas |

Use `all` para consultar os três.

## Requisitos

- Python 3.12+
- Chromium via Playwright (necessário para ClickBus)
- Conta SMTP para envio de e-mail (opcional em modo dry-run)

## Instalação local

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

## Configuração

1. Copie o exemplo de variáveis de ambiente:

```bash
cp .env.example .env
```

2. Edite o `.env` com e-mail, rota e credenciais SMTP.  
   O arquivo `.env` **não** é versionado.

3. (Opcional) Use `config.example.json` como referência da config persistida em `data/config.json`.

### Variáveis principais

| Variável                                                            | Descrição                                                  |
| ------------------------------------------------------------------- | ---------------------------------------------------------- |
| `NOTIFY_EMAIL`                                                      | Destinatário padrão (também via CLI / comando `set email`) |
| `ORIGIN` / `DESTINATION` / `TRAVEL_DATE`                            | Rota e data da ida (`DD/MM/YYYY`)                          |
| `SEARCH_SITE`                                                       | `all`, `flixbus`, `clickbus` ou `queropassagem`            |
| `SEARCH_LIMIT`                                                      | Máximo de passagens por site                               |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Envio de e-mail                                            |
| `SMTP_TLS`                                                          | `true` / `false`                                           |
| `SMTP_DRY_RUN`                                                      | `true` = não envia; salva HTML em `data/last_email.html`   |
| `BUS_SCRAP_DATA_DIR`                                                | Pasta de dados (`data` localmente)                         |
| `TZ`                                                                | Fuso horário (`America/Sao_Paulo`)                         |

> **Importante:** o `main.py` não carrega o `.env` automaticamente. No Docker Compose as variáveis são injetadas. Em execução local, exporte-as no shell ou use um carregador de `.env`.

### Carregar `.env` no PowerShell

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $name, $value = $_.Split('=', 2)
  Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
}
$env:BUS_SCRAP_DATA_DIR = "data"
$env:SMTP_DRY_RUN = "false"
```

## Uso

### Busca única (sem e-mail)

```bash
python -m bus_scrap --origem Fortaleza --destino Recife --data 15/09/2026 --site all
```

Opções úteis: `--site flixbus|clickbus|queropassagem|all`, `--json`, `--limit`.

### Serviço agendado + e-mail

```bash
python main.py `
  --email seu-email@exemplo.com `
  --origem Fortaleza `
  --destino Recife `
  --data 15/09/2026 `
  --site all `
  --run-now
```

Sem `--run-now`, o serviço fica escutando comandos e dispara o cron no horário configurado (padrão 10:00).

#### Argumentos de inicialização

| Argumento                           | Descrição                             |
| ----------------------------------- | ------------------------------------- |
| `--email`                           | Destinatário                          |
| `--origem` / `--destino` / `--data` | Rota e data da ida                    |
| `--site`                            | Provider(s)                           |
| `--limit`                           | Limite por site                       |
| `--cron-hour` / `--cron-minute`     | Horário do envio diário               |
| `--run-now`                         | Executa uma busca/envio imediatamente |

### Comandos em runtime

Com o serviço rodando, digite no terminal:

```
help
show
set email novo@email.com
set origem Fortaleza
set destino Natal
set data 20/10/2026
set site all
set limit 10
set cron_hour 10
set cron_minute 0
run
quit
```

A configuração fica salva em `data/config.json`.

## Docker (produção)

1. Configure o `.env` (SMTP real, `SMTP_DRY_RUN=false`).
2. Suba o serviço (BuildKit ativo para cache de pip/apt/camadas):

```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
docker compose up -d --build
```

Rebuilds seguintes reaproveitam cache de `pip`, `apt` e da camada do Chromium; só o código da app é recopiado quando muda.

O entrypoint ajusta automaticamente as permissões de `./data` (volume montado) e em seguida roda a aplicação como usuário não-root (`appsvc`).

3. Comandos sem attach (`docker exec`):

```bash
docker exec bus-scrap bus-ctl show
docker exec bus-scrap bus-ctl status
docker exec bus-scrap bus-ctl set destino Natal
docker exec bus-scrap bus-ctl run
docker exec bus-scrap bus-ctl help
```

Ou equivalente: `docker exec bus-scrap python -m bus_scrap.ctl show`.

4. Para digitar comandos no attach interativo:

```bash
docker attach bus-scrap
```

(Use `Ctrl+P Ctrl+Q` para sair do attach sem parar o container.)

Logs e artefatos ficam em `./data` (volume montado).

### Erro `Permission denied: '/app/data/config.json'`

Isso acontece quando a pasta `./data` no host não é gravável pelo usuário do container. Com a imagem atual (entrypoint + `gosu`), um rebuild resolve:

```bash
docker compose up -d --build --force-recreate
```

Workaround manual (se ainda necessário):

```bash
sudo chown -R 10001:10001 ./data
```

## Estrutura do projeto

```
bus-scrap/
├── main.py                 # Entrada do scheduler (cron + e-mail + comandos)
├── bus_scrap/
│   ├── __main__.py         # CLI de busca única
│   ├── providers/          # FlixBus, ClickBus, QueroPassagem
│   ├── scheduler/          # Config, job, SMTP, cron, comandos
│   └── templates/email.html
├── data/                   # Runtime (ignorado no Git, exceto .gitkeep)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── config.example.json
└── requirements.txt
```

## Logs e dry-run

- Console: mensagens `[INFO]`, `[OK]`, `[WARN]`, `[ERRO]`
- Arquivo: `data/log.txt`
- Dry-run SMTP: HTML gerado em `data/last_email.html`

## Segurança

- Não versionar `.env`, senhas SMTP ou `data/config.json` com e-mail real
- Rotacione credenciais se forem expostas
- Use `.env.example` e `config.example.json` apenas como modelos

## Licença

Uso pessoal / educacional. Respeite os termos de uso dos sites consultados.
