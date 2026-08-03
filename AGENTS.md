# AGENTS.md

Guia para o Codex trabalhar neste repositório. Português (pt-BR) por padrão — o domínio é CLT brasileira e os identificadores no código são em português.

## O que é o projeto

App web (Flask) para gestores acompanharem férias de funcionários em múltiplas empresas. Responde: **o funcionário já tem direito a férias?**, alerta **vencidas / a vencer**, e permite **programar férias** respeitando o aviso prévio.

Dados originais vêm da planilha `Controle_Ferias_Master_Geral.xlsx` (3 empresas, ~80 funcionários, ~113 períodos aquisitivos), importada via `flask import-xlsx`.

## Stack

- Python 3.12 (3.14 funciona localmente com SQLite). Railway usa 3.12 — ver `.python-version`.
- Flask 3 + Flask-SQLAlchemy 3 + Flask-Migrate + Flask-WTF.
- SQLAlchemy 2 / psycopg 3 em prod; SQLite local.
- Jinja2 + design system próprio "Editorial Risk": CSS estático único (`app/static/css/app.css`, tokens claro/escuro via `html[data-theme]`) + JS vanilla (`app/static/js/app.js`) — **sem build, sem Tailwind**. Fontes via Google Fonts (CDN): Archivo, Instrument Serif, Space Mono.
- openpyxl para o importer; requests para chamar a Z-API (WhatsApp).
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
flask import-xlsx .\Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026
flask import-setores .\Controle_Ferias_Master_Geral.xlsx   # setores (coluna B)
flask seed-setores
flask verificar-saldos                 # confere o saldo derivado (read-only)

# primeiro admin (uma vez por ambiente — não tem fallback de senha única)
flask criar-gestor --email admin@exemplo.com --nome "Admin" --admin

# rodar
flask run                              # http://localhost:5000

# alertas WhatsApp (Z-API) — config no HUD /integracoes/zapi; cron chama isto
flask enviar-alertas-zapi --dry-run    # monta e imprime o resumo, sem enviar

# testes
pytest -q
```

## Arquitetura (resumo)

```
app/
  __init__.py     factory; registra blueprints; injeta STATUS_LABELS/BADGE/hoje/current_user no Jinja
  config.py       env vars; normaliza DATABASE_URL do provedor (Railway/Render) para postgresql+psycopg://
  models.py       Gestor, Empresa, Setor, Funcionario, PeriodoAquisitivo, ProgramacaoFerias, ConfiguracaoZapi, EnvioZapi
  status.py       status E saldo derivados (funções puras, sem DB) — base_periodo/saldo_periodo; LABELS/CLASS/VAR
  periodos.py     janelas aquisitivas virtuais (funções puras, sem DB) — periodos_efetivos/janelas_virtuais
  tempo.py        marcos de tempo de serviço (funções puras, sem DB) — 45/90/120 dias e aniversários a partir da data de admissão; dia de aviso por antecedência; marcos passados (ultimo_marco) e por janela (marcos_no_intervalo/resumo_marcos)
  dashviz.py      agregações do painel (donut, timeline, heatmap, trend, risco) — consome status.py, NÃO importa db
  importer.py     parsing do XLSX (multi-linha por funcionário, serial→data, decimais)
  zapi.py         cliente HTTP da Z-API (WhatsApp); redige tokens em logs/erros
  zapi_digest.py  monta o resumo de férias (puro, reusa status.py); render seguro de modelos
  icons.py        ICONS: SVGs inline (set de ícones de linha do redesenho)
  uihelpers.py    iniciais() e avatar_cor() (avatar determinístico)
  cli.py          comandos Flask: import-xlsx (--data-referencia), verificar-saldos, import-setores, seed-setores, criar-gestor, bootstrap-admin, enviar-alertas-zapi
  auth.py         login por email/senha (Gestor); helpers current_user, login_required, admin_required
  forms.py        Flask-WTF (Login, Programação, Gestor, MudarSenha, ConfiguracaoZapi)
  routes/         dashboard, funcionarios, tempo (Tempo Funcionários, admin-only), gestores, programacao, setores, configuracoes (conta do gestor), integracoes (HUD Z-API/WhatsApp, admin)
  templates/      Jinja2 (design "Editorial Risk"); _macros.html (icon, status_pill, avatar, nav, brand…)
  static/         css/app.css (design system, claro/escuro), js/app.js (toggles + animações resilientes)
migrations/       Alembic — DEVE ser commitada
seeds/setores.py  setores padrão
tests/            test_status.py, test_importer.py, test_programacao.py, test_auth.py, test_gestores.py, test_zapi.py, conftest.py
```

## Regras de domínio (CLT) — ler antes de mexer em status/programação/saldo

**O saldo é DERIVADO, nunca armazenado**: `saldo = base_periodo − dias_programados`
(`app/status.py`). A coluna `PeriodoAquisitivo.saldo_snapshot` (ex-`dias_restantes`)
é o AG da planilha na data-retrato (`snapshot_em`) e **nunca é mutada pelo app**.

- **base_periodo**, dois regimes por período:
  - fechado na data-retrato (`fim <= snapshot_em`): base = `saldo_snapshot` — o AG
    embute férias gozadas antes do app;
  - qualquer outro (aberto no retrato, ou criado pelo app com `snapshot_em` nulo):
    **30 dias ao fechar** (art. 130, caput; faltas fora de escopo) e acúmulo
    proporcional de 2,5/mês completado enquanto em formação.
- **Programações consomem saldo enquanto a linha existir** — programar cria a linha
  (débito implícito), cancelar apaga (devolução implícita). Nada de mutar coluna.
- **Janelas virtuais** (`app/periodos.py`): os períodos seguintes ao último do banco
  são derivados de hoje (12 meses sucessivos; `limite_gozo` = fim + 12 meses) e só
  viram linha quando o usuário programa contra eles (materialização on-demand em
  `routes/programacao`, `snapshot_em` nulo). Funcionário sem período nenhum ancora
  na `data_admissao`; inativo não gera; período com `fim` nulo suspende a geração.
- **Período aquisitivo**: 12 meses; ao fechar (fim ≤ hoje), nasce o direito a férias.
- **Tem direito**: período aquisitivo fechado **E** saldo derivado > 0.
- **A vencer**: faltam ≤ `ALERTA_A_VENCER_DIAS` (padrão 60) para o `limite_gozo` (fim do concessivo).
- **Vencida**: passou do `limite_gozo` com saldo > 0 → risco de pagamento em dobro.
- **Programada**: existe `ProgramacaoFerias` ligada ao período cujo fim ≥ hoje.
- **Em formação**: período ainda não fechou (fim no futuro ou nulo).
- **Quitada**: período fechado com saldo derivado <= 0.
- Na lista, **"Dias disp."** = soma do saldo derivado de todos os períodos fechados
  (programação parcial entra com o resíduo; quitado soma 0; "—" só sem período fechado).

Precedência (pior caso primeiro): `VENCIDA > A_VENCER > TEM_DIREITO > PROGRAMADA > EM_FORMACAO > QUITADA`. Ver `app/status.py`.

- **Aviso prévio de 30 dias** (`AVISO_PREVIO_DIAS` em `routes/programacao.py`): exigido na programação manual para gestores comuns. **Admin é isento** — pode programar a partir de hoje; datas no passado continuam bloqueadas para todos.

**Invariante crítico:** status e saldo **nunca são persistidos**. São sempre recalculados a partir de `date.today()`. Não adicionar coluna de status nem mutar `saldo_snapshot` nos modelos.

## Integração WhatsApp (Z-API)

Aviso ativo de férias por WhatsApp, **todo configurável pelo admin** no HUD `/integracoes/zapi` (item "WhatsApp" na nav, admin-only) — credenciais, regras e modelos de mensagem ficam no **banco**, não em env var.

- **Modelos** (`app/models.py`): `ConfiguracaoZapi` é um **singleton** (id=1; use sempre `ConfiguracaoZapi.obter()`, que cria a linha sob demanda e é robusto a corrida entre workers) e `EnvioZapi` é o log de cada disparo (histórico no HUD + trava anti-duplicação).
- **Destinatários** são números avulsos (um por linha) que recebem um **resumo geral** das pendências — não há telefone por funcionário/gestor.
- **Tempo de serviço (marcos por admissão):** a página **Tempo Funcionários** (`/tempo-funcionarios`, blueprint `tempo`, item de nav abaixo de Funcionários, **admin-only**) lista, por colaborador ativo, o tempo de casa, o **último marco batido** (com "há quanto tempo") e o próximo, destacando os que avisam hoje. A lógica é pura em `app/tempo.py` (sem DB, como `status.py`): marcos de **45 dias** e **90 dias** (avisam 5 dias antes), **120 dias** (avisa no dia) e **aniversários** — 1 ano e, sucessivamente, todos os anos (avisam 2 dias antes). Um marco "alerta hoje" quando `data_marco - antecedência == hoje` (disparo único; não há janela). Esses marcos entram **no mesmo resumo do WhatsApp**: `zapi_digest.coletar_marcos` é varrido junto com `coletar_itens` no comando agendado e no "enviar teste", e `montar_mensagem` anexa um bloco de tempo de serviço (toggle `notificar_tempo_servico` + modelos `modelo_tempo_cabecalho`/`modelo_tempo`, editáveis no HUD). **Limitação:** como os demais gates, o aviso é de dia exato — se a janela do cron pular o dia (fim de semana com `apenas_dias_uteis`, downtime), aquele aviso não sai.
- **Filtros e vistas da página Tempo Funcionários** (`app/routes/tempo.py`): busca (nome/código), **empresa**, **setor**, **faixa de tempo de casa** (`tempo.FAIXAS_TEMPO`) e **tipo de marco em múltipla escolha** (chips; `?marco=45&marco=aniversario` — `getlist` também aceita as URLs antigas de valor único). Um **seletor de mês** (`?mes=AAAA-MM`, padrão o corrente; lixo cai no corrente sem 500) governa o painel "Marcos do mês" (total / já batidos / a bater, com quebra por tipo) e a vista `?vista=linha` — **linha do tempo**: uma linha por marco do mês, batidos e a bater, em ordem de data. A vista padrão (`colaborador`) é uma linha por pessoa. **Regras que não devem ser trocadas sem pedir:** o painel "Avisos de hoje" **ignora os filtros** de propósito (ele espelha o disparo do WhatsApp, que não conhece filtro de tela), enquanto o painel do mês os respeita; e os chips filtram "o marco em foco" — os do mês na linha do tempo (ou com `?no_mes=1`), o próximo marco no resto. Como o mês e os chips são controlados por link e os demais filtros por `<form method=get>`, o formulário carrega `mes`/`vista`/`marco`/`no_mes` em **hidden inputs** para não derrubá-los ao submeter.
- **Builder** `app/zapi_digest.py` (puro): `coletar_itens` reusa `app/status.py` e filtra pelas regras (`notificar_vencida/a_vencer/tem_direito`, `antecedencia_dias`); `coletar_marcos` reusa `app/tempo.py` (marcos do dia); `montar_mensagem` faz **render seguro** dos modelos — `re.sub(r"\{(\w+)\}", …)`, chave desconhecida ou `{` solto ficam intactos. **Nunca usar `str.format`** (quebra com `KeyError`/`{` literal). Teto `MAX_LINHAS` (excedente vira "…e mais N").
- **Cliente** `app/zapi.py`: `enviar_texto` (timeout; sucesso só com `messageId`/`zaapId`; nunca levanta). **Segurança:** o `instance_token` vai no PATH da URL e o `client_token` no header — `_redigir` remove os tokens de qualquer `detalhe`/log; o HUD nunca re-renderiza os tokens (PasswordField, **branco-mantém**, badge "configurado").
- **Envio agendado:** `flask enviar-alertas-zapi [--force] [--dry-run]` (`app/cli.py`). Pensado para um **cron de hora em hora**: auto-restringe por `hora_envio` (hora **local** — depende de `TZ`), `apenas_dias_uteis`, e trava anti-dup **por destinatário** (`EnvioZapi` `ok` com `data_referencia` = hoje → retry de falha parcial + dedup numa regra só). `--force` ignora os gates; `--dry-run` só imprime. O botão "Enviar teste" do HUD (`/integracoes/zapi/testar`, `tipo=teste`) faz o mesmo bypass para validar a config.
- **Invariante preservada:** `EnvioZapi` guarda entrega + contagem do instante — nunca o status de férias (que continua derivado de `date.today()`).
- **Limitações (não "corrigir" sem pedir):** `apenas_dias_uteis` ignora feriados (só seg–sex); tokens em texto plano no banco (Postgres gerenciado).

## Convenções

- Código de domínio em **português** (nomes de funções, variáveis, modelos). Manter o padrão ao editar.
- **Datas sempre em dd/mm/aaaa** (pt-BR), na exibição (`strftime('%d/%m/%Y')`) e na digitação. Campos de data usam `CampoDataBR` (`app/forms.py`): input de texto com máscara (`[data-mask="data"]` em `app.js`), parse em `%d/%m/%Y` com fallback ISO. **Não usar `<input type="date">` nativo** — o formato de exibição dele segue o locale do navegador, não o do app.
- `status.py` é **puro** — sem acesso a `db`. Manter assim para facilitar teste e raciocínio.
- O importer mapeia colunas do XLSX por letra (Q, R, AC, AG, AH, Z, AB). Se mudar o layout da planilha, atualizar `importer.py` e `test_importer.py` juntos. As colunas W/X (gozo programado na planilha) são **ignoradas de propósito** — programação de férias nasce só no app.
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
- Variáveis a configurar manualmente no painel: `DATABASE_URL`, `SECRET_KEY`, `FLASK_APP=app:create_app`, `TZ=America/Sao_Paulo` (opcional — `app/__init__.py` já assume esse fuso por padrão; a var prevalece), `ALERTA_A_VENCER_DIAS` (opcional), `ADMIN_EMAIL` + `ADMIN_SENHA` (+ `ADMIN_NOME` opcional) para o bootstrap do admin.
- Domínio público: **Settings → Networking → Generate Domain**.
- `flask db upgrade` roda a cada deploy (parte do `startCommand`).
- **Cron do WhatsApp (Z-API):** crie um **serviço de cron separado** (mesma imagem) com schedule **horário em UTC** (`0 * * * *`) e comando `flask enviar-alertas-zapi`. Esse serviço **não** roda `flask db upgrade` (quem migra é o web). Variáveis dele: `DATABASE_URL`, `SECRET_KEY` e **`TZ=America/Sao_Paulo`** (sem `TZ`, o gate de `hora_envio` roda em UTC). O comando se auto-restringe (hora/dia útil/anti-dup) → no máximo um envio/dia. A config (credenciais/regras/modelos) é feita no HUD `/integracoes/zapi`, não em env var. **Não** usar APScheduler in-process (gunicorn pode ter N workers → N agendadores → duplicação).
- Import inicial via Railway CLI (planilha fica local — está no `.gitignore`):
  - dry-run: `railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026 --dry-run`
  - real: `railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026`
  - conferência: `railway run flask verificar-saldos` (read-only) antes e depois
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
- **Remover funcionário = inativar (soft-delete):** `Funcionario.ativo` (migration `63859db4e304`, backfill `server_default=true`). Inativo some das listas e do painel e bloqueia programação; admin reativa pelo detalhe (lista tem toggle admin `?inativos=1`). **Filtragem do `ativo` mora em exatamente 2 queries de lista** (`dashboard.index`, `funcionarios.listar`) — ao criar novos caminhos de query de `Funcionario`, lembrar de aplicar o filtro. Funcionário criado manualmente nasce sem linhas de período, mas a janela aquisitiva virtual ancora na `data_admissao` — ele acumula e ganha direito sozinho (sem admissão, nada aparece).
- **Login** é por gestor identificado (email/senha). Sem reset por email. O gestor troca a **própria** senha em **Configurações** (`/configuracoes/senha`, exige a senha atual; entrada pela engrenagem no menu do usuário); o admin também reseta a de qualquer gestor via `/gestores/<id>/senha`. A senha do admin de `ADMIN_EMAIL` é recuperável trocando `ADMIN_SENHA` e refazendo o deploy (ver Deploy) — **atenção:** como ela é ressincronizada a cada deploy, se *esse* admin trocar a senha pela UI ela será sobrescrita pelo valor de `ADMIN_SENHA` no próximo deploy.
- **Acesso por setor (não por empresa):** o filtro de visão é por **setor**, não por empresa — um gestor não-admin de "Produção" vê Produção em **todas** as empresas. Admin atribui o setor ao gestor no cadastro (`/gestores/novo`) ou em `/gestores/<id>/editar`. **Consequência da migration `a15c6bf0c3a1`:** todo gestor não-admin pré-existente fica com `setor_id = NULL` e **não vê nada** até um admin atribuir um setor — é o efeito esperado de exigir setor para não-admin, não um bug. Gestor não-admin sem setor → listas/painel vazios e 403 nos detalhes.
- **Programações nascem só no app:** o importer ignora as colunas W/X da planilha e nunca cria nem remove `ProgramacaoFerias` (a migration `c7d1a9e4f2b8` apagou as antigas `origem=import`, devolvendo o saldo das não encerradas). A planilha é base apenas de funcionários, períodos e saldos. **Atenção:** re-importar sobrescreve `saldo_snapshot`/`snapshot_em` com a planilha, mas NÃO apaga o consumo do app (que mora nas linhas de `ProgramacaoFerias`). O risco restante é a planilha nova já descontar férias registradas no app → dupla contagem; rode `flask verificar-saldos` após qualquer import (saldo negativo denuncia).
- **Abono, 13º, faltas** estão fora de escopo nesta versão — valores importados são exibidos mas não editáveis.

## Ao trabalhar aqui

- Não armazenar status calculado no banco.
- Ao mexer em regras de status, atualizar `app/status.py` **e** `tests/test_status.py` juntos.
- Ao mexer no importer, rodar `pytest tests/test_importer.py` contra a planilha real local.
- Não introduzir dependências pesadas (build tools front, ORMs alternativos) sem motivo claro — o projeto é deliberadamente enxuto.
