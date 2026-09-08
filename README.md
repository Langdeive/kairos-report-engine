# Kairós Report Engine

Ferramenta local operada pelo Hermes para extrair e normalizar o **Relatório do Coach** da
Tutory e gerar os relatórios mensais de evolução da Kairós Mentorias.

> **Estado atual:** a extração direta da Tutory, a normalização, o pacote canônico de dados, a
> retomada segura de lotes e o primeiro gerador com os layouts aprovados já estão implementados.
> A primeira versão não exige comentários. O Hermes executa a extração, gera os PDFs e usa
> a lista local de destinatários para enviar via Baileys. A ferramenta não envia mensagens;
> aprovação, registro dos envios e prevenção de reenvios na operação ficam com o Hermes.

## O que já funciona

- acesso à Tutory por chamadas HTTP, sem cliques recorrentes no navegador;
- descoberta completa dos alunos ativos, com conferência do total informado pela plataforma;
- geração e leitura do Relatório do Coach por aluno;
- normalização das métricas em um formato interno estável;
- armazenamento local em SQLite;
- proteção do telefone armazenado;
- execução retomável: uma interrupção não refaz relatórios já concluídos;
- telefone inválido bloqueia somente a entrega, sem impedir a extração acadêmica;
- exportação de um registro por aluno, inclusive quando os dados estão bloqueados ou pendentes;
- cálculos derivados sem inventar métricas ausentes;
- geração de PDF com capa, panorama mensal, constância, questões, três piores disciplinas e mapa
  completo das disciplinas;
- comandos de diagnóstico, criação, extração, consulta e exportação do ciclo.

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

Somente em instalação nova, gere uma chave local de proteção dos telefones. Em atualizações,
preserve a chave existente junto do banco; trocar a chave impede ler os telefones já salvos:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Configuração

| Variável | Finalidade |
| --- | --- |
| `TUTORY_API_TOKEN` | Opcional; compatibilidade de emergência com token estático |
| `TUTORY_ACCOUNT` | Conta usada no login automático da Tutory |
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
uv run kairos-report data export --run 1
uv run kairos-report report generate-batch --run 1
uv run kairos-report data export-delivery --run 1
uv run kairos-report report generate --input caminho/relatorio.json --output caminho/relatorio.pdf
uv run kairos-report report generate-live --month 2026-08 --student-id ID_TUTORY --data-output caminho/dados.json --output caminho/relatorio.pdf --previews caminho/previas
```

O gerador usa por padrão a logo, a capa-base e as fontes aprovadas que acompanham o projeto. Os
parâmetros `--logo`, `--cover-template` e `--font-dir` permitem substituir esses ativos sem alterar
o código, caso a identidade visual mude futuramente.

Se as configurações estiverem no arquivo `.env`, use `uv run --env-file .env kairos-report ...`.
O carregamento do arquivo é feito pelo uv; a aplicação lê as variáveis de ambiente.

Para testes de lote, prefira `run extract --run ID --student ID_TUTORY`; repita `--student`
para vários alunos. A seleção é congelada no ciclo e não muda na retomada. Sem a opção na
primeira execução, todos os ativos conferidos entram no ciclo. Os parâmetros de espera e
tentativas estão em `.env.example` e explicados no `HERMES_HANDOFF.md`.
Retenção, horário e modo de aprovação são configurações; não criam sozinhos limpeza,
agendamento ou fila de aprovação/entrega no Hermes.

`run extract` consulta desempenho, questões e atividades e persiste as três fontes. Depois,
`report generate-batch --run ID` gera os PDFs aprovados dos registros válidos e informa quais
registros foram ignorados. PDFs já aprovados ou enviados não são sobrescritos por esse comando.
O resultado fica em `review/AAAA-MM/run-ID/pdf`, com caminho e hash registrados no banco.

A geração do lote também grava `review/AAAA-MM/run-ID/delivery-manifest.json`. Cada item
contém `report_id`, `student_id`, `student_name`, `phone` (ex.: `5511999991234`), `pdf_path`,
`pdf_sha256`, `ready_for_hermes` e `issues`. O telefone vem da ficha do aluno na Tutory,
é normalizado e permanece criptografado no banco. A lista local contém o número legível
necessário ao envio e não deve ir para o GitHub. O PDF e o pacote acadêmico não contêm telefone.

Hermes deve usar somente os itens com `ready_for_hermes=true`; telefone inválido, PDF ausente
ou alterado e registros marcados como enviados são sinalizados. A lista não é uma fila com
reserva: o Hermes mantém seu próprio registro de envios e não deve reenviar a mesma combinação
de conta, ID Tutory, período, revisão e `pdf_sha256`. O `report_id` identifica o registro
somente dentro daquele banco; pode se repetir em um banco de teste. Exportar novamente a lista
não marca mensagens como enviadas. A aprovação precisa corresponder aos hashes atuais.
`data export-delivery` permite atualizar a lista sem gerar os PDFs novamente. A saída do
terminal mostra apenas caminho e contagens, sem os números completos.

### Seções sem dados

- Sem horas: uma página de constância informa a ausência de registros, sem gráficos zerados.
- Sem questões: uma página informa a ausência; prioridades e mapa são omitidos.
- Só horas ou só questões: a seção com dados permanece completa.
- Fonte de questões ausente em dados antigos: mensagem de indisponibilidade, sem afirmar zero.
- Sem metas ou sem detalhes semanais/modalidades: mensagem específica no respectivo quadro.
- Zero acertos com questões respondidas: o desempenho de 0% permanece visível.
- Muitos assuntos: continuação automática, sem desenhar fora dos cartões.

Consulte a revisão do fluxo em `docs/review-2026-09-05.md` para evidências e limites conhecidos.

O comando `report generate-live` é um diagnóstico legado para um único aluno. Ele faz o login
HTTP e gera o PDF, mas não possui as proteções de seleção congelada, bloqueio de execução e
retomada durável do fluxo de lote. Não deve ser usado como rotina operacional nem como etapa
de validação para liberar o lote. Para testar um aluno, use `run extract --student ID` e depois
`report generate-batch`, conforme o fluxo acima. Nenhum desses comandos envia pelo WhatsApp.

O comando `doctor` não exibe credenciais. A rotina real deve começar com um aluno controlado e
avançar para o lote completo apenas depois da conferência do resultado.

Na operação normal, a ferramenta cria a sessão com `TUTORY_ACCOUNT` e `TUTORY_PASSWORD` e obtém
a autorização da API automaticamente. Não é necessário abrir o navegador nem renovar um token
manualmente a cada ciclo.

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
- [Contrato do pacote de dados do relatório](docs/contracts/report-data-package.md)
- [Handoff operacional para o Hermes](HERMES_HANDOFF.md)

## Segurança e privacidade

Este repositório contém apenas código, documentação e dados sintéticos. Credenciais, cookies,
tokens reais, telefones, nomes de alunos, PDFs e arquivos HAR devem permanecer fora do Git.
Como o repositório é público, qualquer diagnóstico novo deve ser sanitizado antes de um commit.
A foto, logo e capa da mentoria são ativos de identidade visual aprovados pelo responsável;
isso não autoriza publicar dados de alunos. As fontes acompanham suas licenças OFL.

## Licença

Nenhuma licença de reutilização foi concedida neste momento. A visibilidade pública permite
consultar e clonar o código, mas não altera os direitos autorais do projeto.
