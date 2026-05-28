# CLAUDE.md

Guia para o Claude Code trabalhar neste repositório. Português (pt-BR) por padrão — o domínio é CLT brasileira e os identificadores no código são em português.

## O que é o projeto

App web (Flask) para gestores acompanharem férias de funcionários em múltiplas empresas. Responde: **o funcionário já tem direito a férias?**, alerta **vencidas / a vencer**, e permite **programar férias** respeitando o aviso prévio.

Dados originais vêm da planilha `Controle_Ferias_Master_Geral.xlsx` (3 empresas, ~80 funcionários, ~113 períodos aquisitivos), importada via `flask import-xlsx`.

## Stack

- Python 3.12 (3.14 funciona localmente com SQLite). Render usa 3.12 — ver `runtime.txt`.
- Flask 3 + Flask-SQLAlchemy 3 + Flask-Migrate + Flask-WTF.
- SQLAlchemy 2 / psycopg 3 em prod; SQLite local.
- Jinja2 + Tailwind (CDN, sem build).
- openpyxl para o importer.
- pytest para testes.

## Comandos

```powershell
# setup
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # ajusta APP_PASSWORD / SECRET_KEY

# banco
flask db upgrade                       # aplica migrations
flask db migrate -m "mensagem"         # gera nova migration após mudar models.py
flask import-xlsx .\Controle_Ferias_Master_Geral.xlsx
flask seed-setores

# rodar
flask run                              # http://localhost:5000

# testes
pytest -q
```

## Arquitetura (resumo)

```
app/
  __init__.py     factory; registra blueprints; injeta STATUS_LABELS/BADGE/hoje no Jinja
  config.py       env vars; normaliza DATABASE_URL do Render para postgresql+psycopg://
  models.py       Empresa, Setor, Funcionario, PeriodoAquisitivo, ProgramacaoFerias
  status.py       lógica de status (funções puras, sem DB) — derivada de hoje
  importer.py     parsing do XLSX (multi-linha por funcionário, serial→data, decimais)
  cli.py          comandos Flask: import-xlsx, seed-setores
  auth.py         login por senha única (APP_PASSWORD)
  forms.py        Flask-WTF
  routes/         dashboard, funcionarios, programacao
  templates/      Jinja2 + Tailwind (CDN)
migrations/       Alembic — DEVE ser commitada
seeds/setores.py  setores padrão
tests/            test_status.py, test_importer.py, test_programacao.py, conftest.py
```

## Regras de domínio (CLT) — ler antes de mexer em status/programação

- **Período aquisitivo**: 12 meses; ao fechar (fim ≤ hoje), nasce o direito a férias.
- **Tem direito**: período aquisitivo fechado **E** `dias_restantes > 0`.
- **A vencer**: faltam ≤ `ALERTA_A_VENCER_DIAS` (padrão 60) para o `limite_gozo` (fim do concessivo).
- **Vencida**: passou do `limite_gozo` com saldo > 0 → risco de pagamento em dobro.
- **Programada**: existe `ProgramacaoFerias` ligada ao período cujo fim ≥ hoje.
- **Em formação**: período ainda não fechou (fim no futuro ou nulo).
- **Quitada**: período fechado com `dias_restantes <= 0`.

Precedência (pior caso primeiro): `VENCIDA > A_VENCER > TEM_DIREITO > PROGRAMADA > EM_FORMACAO > QUITADA`. Ver `app/status.py`.

**Invariante crítico:** o status **nunca é persistido**. É sempre recalculado a partir de `date.today()`. Não adicionar colunas de status nos modelos.

## Convenções

- Código de domínio em **português** (nomes de funções, variáveis, modelos). Manter o padrão ao editar.
- `status.py` é **puro** — sem acesso a `db`. Manter assim para facilitar teste e raciocínio.
- O importer mapeia colunas do XLSX por letra (Q, R, AC, AG, AH, Z, AB, W, X). Se mudar o layout da planilha, atualizar `importer.py` e `test_importer.py` juntos.
- `flask db migrate` após qualquer alteração em `models.py`; commitar o arquivo gerado em `migrations/versions/`.
- Tailwind via CDN — não introduzir build de front-end sem necessidade real.
- CSRF: `Flask-WTF` é usado nos formulários; rotas POST sem form (`/logout`, `/funcionarios/<id>/setor`) propositalmente não validam CSRF (ferramenta interna). Documentado no README.

## Deploy (Render)

- `render.yaml` provisiona web service + Postgres.
- `APP_PASSWORD` definido manualmente no painel (sync: false).
- `flask db upgrade` roda a cada deploy.
- Import inicial via Render Shell: `flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx`.
- `DATABASE_URL` do Render começa com `postgres://` — `config.py` normaliza para `postgresql+psycopg://`.

## Limitações conhecidas (não "corrigir" sem pedir)

- **Setor por funcionário** não vem da planilha — começa "Não definido", atribuído via edição inline.
- **Login** é senha única compartilhada. Há gancho em `auth.py` para evoluir.
- **Abono, 13º, faltas** estão fora de escopo nesta versão — valores importados são exibidos mas não editáveis.

## Ao trabalhar aqui

- Não armazenar status calculado no banco.
- Ao mexer em regras de status, atualizar `app/status.py` **e** `tests/test_status.py` juntos.
- Ao mexer no importer, rodar `pytest tests/test_importer.py` contra a planilha real local.
- Não introduzir dependências pesadas (build tools front, ORMs alternativos) sem motivo claro — o projeto é deliberadamente enxuto.
