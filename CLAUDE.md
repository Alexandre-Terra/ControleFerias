# CLAUDE.md

Guia para o Claude Code trabalhar neste repositório. Português (pt-BR) por padrão — o domínio é CLT brasileira e os identificadores no código são em português.

## O que é o projeto

App web (Flask) para gestores acompanharem férias de funcionários em múltiplas empresas. Responde: **o funcionário já tem direito a férias?**, alerta **vencidas / a vencer**, e permite **programar férias** respeitando o aviso prévio.

Dados originais vêm da planilha `Controle_Ferias_Master_Geral.xlsx` (3 empresas, ~80 funcionários, ~113 períodos aquisitivos), importada via `flask import-xlsx`.

## Stack

- Python 3.12 (3.14 funciona localmente com SQLite). Railway usa 3.12 — ver `.python-version`.
- Flask 3 + Flask-SQLAlchemy 3 + Flask-Migrate + Flask-WTF.
- SQLAlchemy 2 / psycopg 3 em prod; SQLite local.
- Jinja2 + design system próprio "Editorial Risk": CSS estático único (`app/static/css/app.css`, tokens claro/escuro via `html[data-theme]`) + JS vanilla (`app/static/js/app.js`) — **sem build, sem Tailwind**. Fontes via Google Fonts (CDN): Archivo, Instrument Serif, Space Mono.
- openpyxl para o importer.
- pytest para testes.

## Comandos

```powershell
# setup
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # ajusta SECRET_KEY

# banco
flask db upgrade                       # aplica migrations
flask db migrate -m "mensagem"         # gera nova migration após mudar models.py
flask import-xlsx .\Controle_Ferias_Master_Geral.xlsx
flask import-setores .\Controle_Ferias_Master_Geral.xlsx   # setores (coluna B)
flask seed-setores

# primeiro admin (uma vez por ambiente — não tem fallback de senha única)
flask criar-gestor --email admin@exemplo.com --nome "Admin" --admin

# rodar
flask run                              # http://localhost:5000

# testes
pytest -q
```

## Arquitetura (resumo)

```
app/
  __init__.py     factory; registra blueprints; injeta STATUS_LABELS/BADGE/hoje/current_user no Jinja
  config.py       env vars; normaliza DATABASE_URL do provedor (Railway/Render) para postgresql+psycopg://
  models.py       Gestor, Empresa, Setor, Funcionario, PeriodoAquisitivo, ProgramacaoFerias
  status.py       lógica de status (funções puras, sem DB) — derivada de hoje; LABELS/CLASS/VAR
  dashviz.py      agregações do painel (donut, timeline, heatmap, trend, risco) — consome status.py, NÃO importa db
  importer.py     parsing do XLSX (multi-linha por funcionário, serial→data, decimais)
  icons.py        ICONS: SVGs inline (set de ícones de linha do redesenho)
  uihelpers.py    iniciais() e avatar_cor() (avatar determinístico)
  cli.py          comandos Flask: import-xlsx, import-setores, seed-setores, criar-gestor, bootstrap-admin
  auth.py         login por email/senha (Gestor); helpers current_user, login_required, admin_required
  forms.py        Flask-WTF (Login, Programação, Gestor, MudarSenha)
  routes/         dashboard, funcionarios, gestores, programacao, setores
  templates/      Jinja2 (design "Editorial Risk"); _macros.html (icon, status_pill, avatar, nav, brand…)
  static/         css/app.css (design system, claro/escuro), js/app.js (toggles + animações resilientes)
migrations/       Alembic — DEVE ser commitada
seeds/setores.py  setores padrão
tests/            test_status.py, test_importer.py, test_programacao.py, test_auth.py, test_gestores.py, conftest.py
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
- Front-end **sem build**: um único `app/static/css/app.css` (design system "Editorial Risk", tokens claro/escuro em `html[data-theme]`) + `app/static/js/app.js` (vanilla). Não introduzir Tailwind/bundler sem necessidade real. Valores de estilo pontuais ficam inline no Jinja (fiéis ao protótipo); classes só para componentes repetidos.
- Tema (claro/escuro) e layout (sidebar↔topnav) são controles de produto, persistidos em `localStorage` (`cf_theme`/`cf_layout`) e aplicados antes do paint por um script inline no `<head>` do `base.html`. **Resiliência (não regredir):** count-up tem fallback por `setTimeout`; entrada anima só `transform` (estado em repouso `opacity:1`); a troca de tema é instantânea (sem `transition` de cor no `body`); respeita `prefers-reduced-motion`.
- Flash: categoria `erro` → alerta inline persistente; demais → toast que some sozinho (`base.html`). Manter a distinção.
- Status → apresentação: `STATUS_LABELS`/`STATUS_CLASS` (classe `.s-*`) e `STATUS_VAR` (nome da CSS var de cor), injetados no Jinja. Ícones via macro `icon()` a partir de `ICONS` (`app/icons.py`).
- CSRF: `Flask-WTF` é usado nos formulários; rotas POST sem form (`/logout`, `/funcionarios/<id>/setor`) propositalmente não validam CSRF (ferramenta interna). Rotas admin de `/gestores/*` usam Flask-WTF e validam CSRF.
- Autenticação: `current_user()` em `auth.py` é a fonte da verdade. Não inspecionar `session["user_id"]` direto fora de `auth.py`. `login_required`/`admin_required` re-buscam o gestor a cada request — desativar um gestor surte efeito imediato.
- **Escopo por setor (autorização):** gestor não-admin só vê/gere funcionários do seu setor (`Gestor.setor_id`); admin vê/gere todos. A regra vive em **dois lugares que devem ficar em sincronia**: `Gestor.pode_gerir(funcionario)` (checagem por objeto — usada em guards de rota e nos templates) e `auth.filtrar_por_escopo(query, gestor)` (mesma regra no nível de query — usada em `dashboard.index` e `funcionarios.listar`). Rotas de mutação/detalhe (`funcionarios.detalhe`, `programacao.programar`) fazem `abort(403)` via `pode_gerir`. Reatribuir setor (`funcionarios.definir_setor`) e gerir funcionários "Não definido" é **admin-only**. Setor é global (cross-empresa): gestor de "Produção" gere Produção nas 3 empresas.

## Deploy (Railway)

- `railway.toml` define builder Railpack e `startCommand` (`flask db upgrade && flask bootstrap-admin && gunicorn ...`).
- `Procfile` espelha o `startCommand` para compatibilidade com qualquer detecção alternativa.
- Postgres é um **plugin separado** no mesmo projeto Railway — vincular via `DATABASE_URL=${{ Postgres.DATABASE_URL }}` no painel de Variables do serviço web.
- Variáveis a configurar manualmente no painel: `DATABASE_URL`, `SECRET_KEY`, `FLASK_APP=app:create_app`, `TZ=America/Sao_Paulo`, `ALERTA_A_VENCER_DIAS` (opcional), `ADMIN_EMAIL` + `ADMIN_SENHA` (+ `ADMIN_NOME` opcional) para o bootstrap do admin.
- Domínio público: **Settings → Networking → Generate Domain**.
- `flask db upgrade` roda a cada deploy (parte do `startCommand`).
- Import inicial via Railway CLI (planilha fica local — está no `.gitignore`):
  - dry-run: `railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx --dry-run`
  - real: `railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx`
  - setores (depois do import acima, pois casa por empresa+código): `railway run flask import-setores ./Controle_Ferias_Master_Geral.xlsx --dry-run` e então sem `--dry-run`
- Admin (bootstrap por ambiente): `flask bootstrap-admin` roda a cada deploy (parte do `startCommand`) e, a partir de `ADMIN_EMAIL`/`ADMIN_SENHA`, **cria** o admin se não existir e **ressincroniza** a senha + reativa/promove (`ativo`, `is_admin`) se já existir. É idempotente e seguro de manter no `startCommand`.
  - Sem `ADMIN_EMAIL`/`ADMIN_SENHA` no painel → o comando é no-op (não há fallback de senha fixa); a instância fica trancada até você configurá-las e refazer o deploy.
  - `ADMIN_SENHA` precisa ter ≥ 6 caracteres — se for menor, o comando falha de propósito e bloqueia o deploy (o deploy anterior continua servindo).
  - **Recuperação de acesso**: troque `ADMIN_SENHA` no painel e refaça o deploy. Cuidado: como a senha é ressincronizada a cada deploy, uma senha alterada pela UI será sobrescrita pelo valor de `ADMIN_SENHA` no próximo deploy.
  - Alternativa pontual (criar sem ressincronizar a cada deploy): `railway run flask criar-gestor --email admin@exemplo.com --nome "Admin" --admin`.
- `DATABASE_URL` do Railway começa com `postgresql://` — `config.py` normaliza para `postgresql+psycopg://`.

## Limitações conhecidas (não "corrigir" sem pedir)

- **Setor por funcionário** vem da coluna B das abas de empresa via `flask import-setores` (texto livre mapeado para vocabulário canônico — `SETOR_CANONICO` no importer); também pode ser ajustado por edição inline. Funcionário sem setor na planilha fica "Não definido" (ex.: a aba `AMP Comercio`).
- **CRUD admin (UI):** o admin pode criar/renomear/excluir **setores** (`/setores`, blueprint `setores`) e adicionar **funcionários** (`/funcionarios/novo`). Excluir setor é **bloqueado** se houver qualquer funcionário (ativo ou inativo) ou gestor associado — para corrigir nome, renomear. Empresa continua vindo só do importer (sem CRUD).
- **Remover funcionário = inativar (soft-delete):** `Funcionario.ativo` (migration `63859db4e304`, backfill `server_default=true`). Inativo some das listas e do painel e bloqueia programação; admin reativa pelo detalhe (lista tem toggle admin `?inativos=1`). **Filtragem do `ativo` mora em exatamente 2 queries de lista** (`dashboard.index`, `funcionarios.listar`) — ao criar novos caminhos de query de `Funcionario`, lembrar de aplicar o filtro. Funcionário criado manualmente nasce sem períodos aquisitivos → aparece como "Em formação" (períodos só vêm do importer).
- **Login** é por gestor identificado (email/senha). Sem reset por email, sem self-service para o gestor mudar a própria senha (apenas admin reseta via `/gestores/<id>/senha`). A senha do admin de `ADMIN_EMAIL` é recuperável trocando `ADMIN_SENHA` e refazendo o deploy (ver Deploy).
- **Acesso por setor (não por empresa):** o filtro de visão é por **setor**, não por empresa — um gestor não-admin de "Produção" vê Produção em **todas** as empresas. Admin atribui o setor ao gestor no cadastro (`/gestores/novo`) ou em `/gestores/<id>/editar`. **Consequência da migration `a15c6bf0c3a1`:** todo gestor não-admin pré-existente fica com `setor_id = NULL` e **não vê nada** até um admin atribuir um setor — é o efeito esperado de exigir setor para não-admin, não um bug. Gestor não-admin sem setor → listas/painel vazios e 403 nos detalhes.
- **Abono, 13º, faltas** estão fora de escopo nesta versão — valores importados são exibidos mas não editáveis.

## Ao trabalhar aqui

- Não armazenar status calculado no banco.
- Ao mexer em regras de status, atualizar `app/status.py` **e** `tests/test_status.py` juntos.
- Ao mexer no importer, rodar `pytest tests/test_importer.py` contra a planilha real local.
- Não introduzir dependências pesadas (build tools front, ORMs alternativos) sem motivo claro — o projeto é deliberadamente enxuto.
