# Kairós Report Engine

Ferramenta local operada pelo Hermes para extrair e normalizar o **Relatório do Coach** da
Tutory e, nas próximas etapas, gerar os relatórios mensais de evolução da Kairós Mentorias.

> **Estado atual:** a extração direta da Tutory, a normalização dos dados e a retomada segura
> de lotes já estão implementadas. Comentários do Hermes, PDF final, aprovação e fila de envio
> pelo WhatsApp ainda não estão prontos. Não use este projeto para enviar relatórios reais antes
> de concluir e validar essas etapas.

## O que já funciona

- acesso à Tutory por chamadas HTTP, sem cliques recorrentes no navegador;
- descoberta completa dos alunos ativos, com conferência do total informado pela plataforma;
- geração e leitura do Relatório do Coach por aluno;
- normalização das métricas em um formato interno estável;
- armazenamento local em SQLite;
- proteção do telefone armazenado;
- execução retomável: uma interrupção não refaz relatórios já concluídos;
- bloqueio individual de telefone inválido, sem interromper o restante do lote;
- comandos de diagnóstico, criação, extração e consulta do ciclo.

## Preparação do ambiente

Requisitos:

- Python 3.12;
- [uv](https://docs.astral.sh/uv/);
- acesso autorizado à conta Tutory.

```bash
git clone https://github.com/Langdeive/kairos-report-engine.git
cd kairos-report-engine
uv sync --python 3.12
```

Copie `.env.example` para `.env` e preencha os valores somente no ambiente local. Nunca envie
o arquivo `.env`, cookies, banco de dados ou relatórios para o GitHub.

Para gerar uma chave local de proteção dos telefones:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Configuração

| Variável | Finalidade |
| --- | --- |
| `TUTORY_API_TOKEN` | Token autorizado para gerar o Relatório do Coach |
| `TUTORY_ACCOUNT` | Conta usada para criar a sessão da Tutory |
| `TUTORY_PASSWORD` | Senha da conta Tutory |
| `KAIROS_DATA_KEY` | Chave Fernet usada para proteger telefones no banco |
| `KAIROS_DATA_DIR` | Pasta persistente de banco, relatórios e diagnósticos |
| `KAIROS_APPROVAL_MODE` | `required` inicialmente; `automatic` somente após validação |
| `KAIROS_RETENTION_MONTHS` | Retenção dos dados, padrão de 12 meses |
| `KAIROS_TIMEZONE` | Fuso horário da execução |
| `KAIROS_RUN_TIME` | Horário planejado para a rotina mensal |

## Comandos disponíveis

```bash
uv run kairos-report version
uv run kairos-report doctor
uv run kairos-report run create --month 2026-08
uv run kairos-report run extract --run 1
uv run kairos-report run status --run 1
```

O comando `doctor` não exibe credenciais. A rotina real deve começar com um aluno controlado e
avançar para o lote completo apenas depois da conferência do resultado.

## Validação para mudanças

```bash
uv run pytest -q
uv run ruff check src tests migrations
uv run mypy src
git diff --check
```

Uma correção do conector deve ser feita em branch separada, acompanhada por testes, e só deve
ser incorporada à versão usada no ciclo mensal depois de aprovação humana.

## Documentação

- [Arquitetura e fluxo aprovado](docs/architecture.md)
- [Contrato observado da Tutory](docs/contracts/tutory-active-students.md)
- [Handoff operacional para o Hermes](HERMES_HANDOFF.md)

## Segurança e privacidade

Este repositório contém apenas código, documentação e dados sintéticos. Credenciais, cookies,
tokens reais, telefones, nomes de alunos, PDFs e arquivos HAR devem permanecer fora do Git.
Como o repositório é público, qualquer diagnóstico novo deve ser sanitizado antes de um commit.

## Licença

Nenhuma licença de reutilização foi concedida neste momento. A visibilidade pública permite
consultar e clonar o código, mas não altera os direitos autorais do projeto.
