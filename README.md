# Controle de Férias (CLT)

Aplicativo web para gestores acompanharem férias de funcionários em múltiplas
empresas. Responde de forma direta: **o funcionário já tem direito a férias?**,
além de alertar **férias vencidas / a vencer** e permitir **programar férias**
respeitando o aviso prévio de 30 dias.

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
copy .env.example .env          # ajuste APP_PASSWORD / SECRET_KEY
flask db upgrade
flask import-xlsx .\Controle_Ferias_Master_Geral.xlsx
flask run
```

Acesse http://localhost:5000 e entre com a senha de `APP_PASSWORD`.

## Testes

```powershell
pytest -q
```

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
   - `APP_PASSWORD` = a senha de acesso compartilhada
   - `FLASK_APP` = `app:create_app`
   - `TZ` = `America/Sao_Paulo`
   - `ALERTA_A_VENCER_DIAS` = `60` (opcional, padrão 60)
4. Em **Settings → Networking**, clique **Generate Domain** para expor o serviço.
5. A cada deploy, `flask db upgrade` cria/atualiza o schema (definido no
   `startCommand` do `railway.toml`).
6. Import inicial (uma vez): conecte-se ao serviço via Railway CLI e rode
   ```
   railway run flask import-xlsx ./Controle_Ferias_Master_Geral.xlsx
   ```
   ou execute pelo painel em **Deployments → … → Run Command**.

> O Postgres do Railway entrega `DATABASE_URL` no formato `postgresql://…` —
> `app/config.py` normaliza para `postgresql+psycopg://` automaticamente.
> A versão do Python vem de `runtime.txt` (lida pelo Nixpacks).

## Estrutura

```
app/
  __init__.py     factory, blueprints, globals de template
  config.py       env vars + normalização da DATABASE_URL
  models.py       Empresa, Setor, Funcionario, PeriodoAquisitivo, ProgramacaoFerias
  status.py       lógica de status (funções puras)
  importer.py     parsing do XLSX (multi-linha, serial→data, decimais)
  cli.py          comandos: import-xlsx, seed-setores
  auth.py         login por senha única
  forms.py        Flask-WTF (login, programação)
  routes/         dashboard, funcionarios, programacao
  templates/      Jinja2 + Tailwind (CDN)
seeds/setores.py  setores padrão
tests/            test_status.py, test_importer.py
```

## Limitações conhecidas / próximos passos

- **Setor**: a planilha não traz setor por funcionário; ele começa "Não definido"
  e é atribuído manualmente na tela de detalhe (edição inline).
- **Login**: senha única compartilhada. Há gancho em `auth.py` para evoluir para
  usuários com perfis por empresa. As rotas de POST sem formulário
  (`/logout`, `/funcionarios/<id>/setor`) não têm proteção CSRF — risco baixo
  numa ferramenta interna; para endurecer, habilite `CSRFProtect` global e
  inclua `{{ csrf_token() }}` nesses formulários.
- Abono, 13º e gestão de faltas estão **fora de escopo** nesta versão (os valores
  importados são exibidos, mas não editáveis).
