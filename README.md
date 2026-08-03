# Controle de Férias (CLT)

Aplicativo web para gestores acompanharem férias de funcionários em múltiplas
empresas. Responde de forma direta: **o funcionário já tem direito a férias?**,
além de alertar **férias vencidas / a vencer** e permitir **programar férias**
respeitando o aviso prévio de 30 dias (administradores são isentos do aviso e
podem programar a partir de hoje; datas no passado ficam bloqueadas para todos).

Os dados são importados da planilha `Controle_Ferias_Master_Geral.xlsx`
(3 empresas, 80 funcionários, 113 períodos aquisitivos).

## Conceitos (CLT)

- **Período aquisitivo** (12 meses): ao completar, gera direito a 30 dias de
  férias (ou menos, conforme já calculado na planilha).
- **Tem direito**: período aquisitivo **fechado** (fim ≤ hoje) **e** com saldo de
  dias > 0.
- **A vencer**: faltam ≤ 60 dias (configurável) para o limite do período
  concessivo.
- **Vencida**: passou do limite do concessivo com saldo > 0 (risco de pagamento
  em dobro).

O status **nunca é armazenado** — é sempre recalculado a partir da data de hoje
(`app/status.py`).

## Rodando localmente

```powershell
py -3.12 -m venv .venv          # 3.14 também funciona localmente (usa SQLite)
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # ajuste SECRET_KEY
flask db upgrade
flask import-xlsx .\Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026
flask criar-gestor --email admin@exemplo.com --nome "Admin" --admin
flask run
```

Acesse http://localhost:5000 e faça login com o email/senha do admin criado
acima. Pela tela **Gestores** (visível apenas para administradores), o admin
cria os demais gestores.

A planilha é apenas a **base inicial** de funcionários, períodos aquisitivos
e saldos na data-retrato — programações de férias nascem exclusivamente dentro
do app (as colunas de gozo da planilha são ignoradas). O `--data-referencia`
(obrigatório) é a data em que o AG foi calculado no Excel, não a data do
comando. O saldo exibido é sempre **derivado**: período fechado depois do
retrato vale 30 dias, menos o que foi programado no app; os períodos seguintes
(janelas "previstas") aparecem sozinhos com o tempo, sem novo import. Re-import
é idempotente e não apaga o consumo feito no app (que mora nas programações),
mas **a planilha nova não pode já descontar férias registradas no app** — isso
contaria em dobro. Após qualquer import, rode `flask verificar-saldos`
(read-only) e confira o resumo; saldo negativo denuncia dupla contagem.

## Testes

```powershell
pytest -q
```

## Alertas por WhatsApp (Z-API)

Resumo das férias pendentes (vencidas / a vencer) enviado por WhatsApp para
números configurados, via [Z-API](https://z-api.io). **Tudo é configurável pelo
admin** na tela **WhatsApp** (`/integracoes/zapi`) — credenciais, regras (quais
status notificar, antecedência, hora do envio) e os modelos de mensagem. Nada
disso vai em variável de ambiente: mora no banco.

- O admin preenche credenciais + destinatários, ajusta as regras/modelos e pode
  **Enviar teste** para validar.
- O envio automático é feito pelo comando `flask enviar-alertas-zapi`, pensado
  para rodar por um **cron** (no Railway, um serviço de cron separado de hora em
  hora). O comando se auto-restringe pela hora/dia configurados e tem trava
  anti-duplicação, então dispara no máximo uma vez por dia.
- Dry-run local (mostra o resumo, sem enviar): `flask enviar-alertas-zapi --dry-run`.

## Deploy no Railway

1. Suba o repositório no GitHub (o `railway.toml` e o `Procfile` já estão incluídos):
   ```powershell
   git init
   git add -A
   git commit -m "Sistema de controle de férias"
   git branch -M main
   git remote add origin <url-do-repo>
   git push -u origin main
   ```
   Garanta que a pasta `migrations/` entre no commit (ela não está no `.gitignore`).
2. No Railway, crie um **New Project → Deploy from GitHub repo** apontando para
   o repositório. Em seguida, dentro do mesmo projeto, adicione um plugin
   **Postgres** (`+ New → Database → PostgreSQL`).
3. No serviço web, em **Variables**, defina:
   - `DATABASE_URL` = `${{ Postgres.DATABASE_URL }}` (referência ao plugin)
   - `SECRET_KEY` = uma chave aleatória forte
   - `FLASK_APP` = `app:create_app`
   - `TZ` = `America/Sao_Paulo` (opcional — o app já assume esse fuso por
     padrão; a var, se setada, prevalece)
   - `ALERTA_A_VENCER_DIAS` = `60` (opcional, padrão 60)
4. Em **Settings → Networking**, clique **Generate Domain** para expor o serviço.
5. A cada deploy, `flask db upgrade` cria/atualiza o schema (definido no
   `startCommand` do `railway.toml`).
6. Instale e linke o Railway CLI (uma vez):
   ```powershell
   # escolha uma:
   iwr -useb https://railway.com/install.ps1 | iex   # script oficial
   npm i -g @railway/cli                             # se tem Node
   winget install --id Railway.Railway               # via winget

   railway login                                     # abre o navegador
   railway link                                      # selecione projeto + serviço web
   ```
   `railway run <comando>` executa localmente com as variáveis do serviço web do
   Railway — inclusive a `DATABASE_URL` apontando para o Postgres remoto.
   A planilha permanece no seu disco (está no `.gitignore`).

7. **Dry-run** contra o Postgres do Railway (não grava — confere contagens e divergências):
   ```powershell
   railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026 --dry-run
   ```
   Saída esperada com a planilha atual: 3 empresas, 80 funcionários, 113 períodos,
   1 programação, sem divergências.

8. Import real (grava no Postgres remoto):
   ```powershell
   railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx --data-referencia 27/05/2026
   ```

9. Crie o primeiro administrador (uma única vez — **não** coloque no
   `startCommand`, isso recriaria/sobrescreveria o admin a cada deploy):
   ```powershell
   railway run flask criar-gestor --email admin@exemplo.com --nome "Admin" --admin
   ```
   Depois logue na aplicação e use a tela **Gestores** para criar os demais.

> O Postgres do Railway entrega `DATABASE_URL` no formato `postgresql://…` —
> `app/config.py` normaliza para `postgresql+psycopg://` automaticamente.
> A versão do Python vem de `.python-version` (lida pelo Railpack).

## Estrutura

```
app/
  __init__.py     factory, blueprints, globals de template
  config.py       env vars + normalização da DATABASE_URL
  models.py       Empresa, Setor, Funcionario, PeriodoAquisitivo, ProgramacaoFerias
  status.py       lógica de status e saldo derivado (funções puras)
  periodos.py     janelas aquisitivas virtuais (funções puras)
  importer.py     parsing do XLSX (multi-linha, serial→data, decimais)
  cli.py          comandos: import-xlsx, verificar-saldos, seed-setores
  auth.py         login por email/senha (modelo Gestor) + decoradores
  forms.py        Flask-WTF (login, programação, gestor)
  routes/         dashboard, funcionarios, gestores, programacao
  templates/      Jinja2 + Tailwind (CDN)
seeds/setores.py  setores padrão
tests/            test_status.py, test_importer.py
```

## Limitações conhecidas / próximos passos

- **Setor**: a planilha não traz setor por funcionário; ele começa "Não definido"
  e é atribuído manualmente na tela de detalhe (edição inline).
- **Login**: por gestor identificado (email/senha). O primeiro admin precisa
  ser criado via `flask criar-gestor --admin` (não há fallback por variável de
  ambiente — uma instância recém-deployada sem admin fica trancada). Todos os
  gestores logados veem todas as empresas: ainda não há filtro de
  visibilidade por empresa/setor. As rotas POST sem formulário Flask-WTF
  (`/logout`, `/funcionarios/<id>/setor`) intencionalmente não validam CSRF —
  risco baixo numa ferramenta interna; as rotas de admin (`/gestores/...`)
  usam Flask-WTF e portanto validam CSRF.
- Abono, 13º e gestão de faltas estão **fora de escopo** nesta versão (os valores
  importados são exibidos, mas não editáveis).
