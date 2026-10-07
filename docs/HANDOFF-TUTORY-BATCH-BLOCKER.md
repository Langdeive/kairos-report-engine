# Handoff — bloqueio da coleta Tutory e geração mensal

## Estado e escopo

Handoff para inspeção por outro agente, a pedido do responsável pela operação. **Não corrigir, gerar novamente ou enviar automaticamente com base neste documento.** O código publicado é um snapshot de diagnóstico, não uma versão liberada para novos lotes.

- Branch: `feat/test-destination-override`.
- Snapshot de código anterior a este documento: `c8b3624`.
- Período: setembro/2026 (01/09 a 30/09).
- Pedido inicial: 50 alunos novos, sem repetir os 100 selecionados nos dois lotes anteriores.
- Apenas 31 novos elegíveis foram selecionados; o responsável autorizou gerar esses 31 e excluir relatórios vazios.
- Estado atual por aluno selecionado: **5 extrações válidas, 1 aluno bloqueado, 25 ainda não extraídos**.
- **Nenhum PDF foi gerado neste lote, nenhuma aprovação de envio foi criada e nenhuma mensagem foi submetida.**
- Existem registros históricos bloqueados e pendentes duplicados entre runs de tentativa. Não somar registros do banco como se fossem alunos únicos.

## Problema atual: causa confirmada, ainda não corrigida

Código: `topic_launch_table_unverified` (persistido genericamente como `tutory_contract_changed`).

A leitura diagnóstica do aluno bloqueado no run 13 confirmou uma página de lançamentos com:

1. Um `div.card.custom-card` com título `h2` **Questões**, título interno `h6` **Suas Questões** e instruções para cadastrar questões.
2. Outro cartão de cadastro.
3. Um terceiro cartão **Suas Questões** com tabela no formato esperado, **50 linhas na primeira página e paginação**.

A mensagem de orientação não significa, por si só, ausência de lançamentos. Ela pode coexistir com uma tabela preenchida. A presença de 50 linhas também não comprova que sejam questões do mês: o filtro mensal deve continuar ocorrendo por data após a coleta completa.

Em `TutoryClient._launch_page`, a correção `c8b3624` procura primeiro o cartão de orientação. Se o encontra e existe qualquer tabela, paginação ou formulário na página, lança `topic_launch_table_unverified`. Essa precedência bloqueia uma página real com tabela e paginação válidas, antes de coletá-las.

**Falha nossa:** o cartão foi inicialmente interpretado como evidência exclusiva de tela vazia. Os testes sintetizaram cartão+tabela como contradição e não representaram a coexistência legítima observada depois ao vivo. Os 381 testes passando não comprovam a correção dessa hipótese de contrato.

### Direção de correção para avaliação do próximo agente

Não implementada neste snapshot:

- Priorizar a tabela de lançamentos validada pelo contrato; coletar e verificar todas as páginas mesmo com cartões de orientação presentes.
- Considerar o formato sem tabela como possível ausência de lançamentos apenas com a estrutura específica completa e sem evidência de paginação/dados não coletados.
- Manter conciliação dos totais e acertos por assunto com o relatório mensal. Fonte vazia com total mensal não zero deve bloquear, não fabricar zeros.
- Criar teste representando os três cartões reais (somente estrutura sanitizada) e revisar o teste que atualmente rejeita toda coexistência de tabela+cartão.
- Conferir primeira página, páginas seguintes, paginação completa, tabela malformada, tabela inesperada/ambígua, autenticação e identidade.
- Evitar uma terceira alteração pontual sem revisar a estratégia de reconhecimento dos formatos. O processamento foi interrompido para inspeção.

## Tentativas e dificuldades anteriores

### 1. Seleção abaixo do pedido

Regras habilitadas: alunos ativos, plano não pausado na data de geração, mínimo de 15 dias de mentoria, elegibilidade verificável. A seleção também excluiu os 100 alunos dos lotes anteriores. Foram encontrados 31 novos elegíveis. A tentativa de seleção exata de 50 parou; depois houve autorização explícita para gerar 31.

### 2. Links repetidos dos menus

Primeira extração real, run 9: 0 válidos, 1 bloqueado.

Causa: menus desktop/mobile repetem **Lançamentos de Questões** com o mesmo destino. O extrator exigia um único anchor DOM.

Correção `ca7a82d`: resolver links relativos/absolutos, validar todos os destinos distintos e aceitar um único destino permitido. Não selecionar cegamente o primeiro link. Manter HTTPS, host/path permitidos e bloqueio de links hostis.

Validação: 360 testes, Ruff/Mypy/diff check, revisão independente e leitura real do painel. Run 10: primeiro aluno extraído e válido. Esse aluno não tinha questões mensais; não servia para comprovar coleta com volume positivo.

### 3. Página sem tabela

Run 11, esperado 30: 3 válidos, 1 bloqueado, 26 pendentes; circuit breaker parou no primeiro erro.

Leitura diagnóstica: página com cartão de orientação completo, nenhuma tabela e nenhuma paginação. Não havia formulário de login. Não se inferiu zero automaticamente.

Correção `c8b3624`: reconhecer exatamente o cartão completo na primeira página, sem tabela/paginação/formulários; devolver linhas vazias pelo caminho normal. A conciliação mensal permaneceu intacta.

TDD observado: falhas esperadas antes da implementação; casos de evidência parcial, tag incorreta, página posterior, tabela/paginação/formulário em conflito e total mensal não zero. Suíte completa: **381 testes, zero falhas/erros**, Ruff e Mypy (34 arquivos) aprovados. Revisão independente não encontrou bloqueios, mas não reproduziu a coexistência real ainda desconhecida.

Run 12: o aluno antes bloqueado foi extraído e validado; o mensal confirmou zero questões. O registro anterior do run 11 foi preservado.

### 4. Coexistência legítima — bloqueio vigente

Run 13, esperado 26: 0 válidos, 1 bloqueado, 25 pendentes. Coleta parou antes de obter o bundle completo. A fase de PDFs não foi executada.

Leitura diagnóstica, sem POST de geração: identificou o cartão de orientação ao lado da tabela real com 50 linhas/paginação. É a causa atual descrita acima. Não houve nova correção nem tentativa de retomada após essa confirmação.

## Runs e reconciliação por aluno

- Run 9: primeiro aluno bloqueado pelo menu repetido; preservado.
- Run 10: 1 válido.
- Run 11: 3 válidos, 1 bloqueado antigo, 26 pendentes históricos.
- Run 12: nova extração válida do aluno bloqueado do run 11; não mutou o registro antigo.
- Run 13: tentativa dos 26 restantes; 1 bloqueado, 25 pendentes.

Os cinco válidos únicos vêm dos runs 10 (1), 11 (3) e 12 (1). Os 25 pendentes e o bloqueado atual estão no run 13. Seleção congelada privada contém exatamente 31 alunos. Retomada deve reconciliar IDs e não refazer fontes válidas nem confiar cegamente nos resumos antigos dos helpers.

## Arquivos de código para inspeção

- `src/kairos_report/tutory/client.py`: `_student_question_launches`, `_launch_link`, `_launch_page`, coleta antes do POST de geração.
- `src/kairos_report/tutory/parser.py`: `parse_question_report`, enriquecimento e `topic_launch_totals_mismatch`.
- `src/kairos_report/analysis_provenance.py`: agregação por assunto/data e validação de evidência.
- `src/kairos_report/runs/service.py`: sessões, seleção congelada, persistência e circuit breaker.
- `src/kairos_report/data/service.py`: export canônico e geração.
- `tests/unit/test_empty_launch_contract.py`: contrato vazio e conflitos sintéticos; revisar pressuposto de coexistência inválida.
- `tests/unit/test_duplicate_launch_navigation.py`: menu repetido válido e destino hostil.
- `tests/unit/test_topic_extraction.py`, `test_launch_pagination_contract.py`, `test_topic_extraction_cli.py`.
- `tests/integration/test_topic_extraction_pipeline.py`.

Commits relevantes:

- `d563a11`: guards de proveniência e amostras por assunto.
- `82a5cdb`: aquisição automática de contagens no extrator normal, RunService/CLI/export.
- `ca7a82d`: menus repetidos.
- `c8b3624`: formato sem tabela; contém o pressuposto que bloqueia a coexistência real.

## Evidências privadas locais — não estão no GitHub

Ambiente operacional usado: `/opt/data/projects/kairos-report-engine-release-5f46684` (Python 3.12, uv). Launcher `/opt/data/bin/kairos-report`. Configuração privada em `.env` de outro checkout operacional; não copiar nem publicar.

Base privada: `/opt/data/kairos-reports/private-review/2026-09/batch-03-31/`.

- `selection.json`: seleção congelada; dados pessoais, não publicar.
- `canary-state.json`, `canary-retry-state.json`, `batch-state.json`: tentativas anteriores.
- `empty-screen-canary-state.json`, `empty-screen-canary-data.jsonl`: run 12 válido.
- `remaining26-state.json`: run 13 iniciado, mas não validado.
- `diagnostic-run11/`: captura de tela sem tabela.
- `diagnostic-run13/`: captura de coexistência de instruções+tabela/paginação, resumo e traceback privados.
- `source-captures/`: bundles completos obtidos. Nem todo bloqueio tem bundle: falhas de aquisição precedem sua gravação.
- `offline-blocker-run13-summary.json`: replay indicou falha antes de bundle completo.
- `resume-empty-failure.json`: interrupção da retomada.

Helpers privados fora do repositório: `resume_batch3_empty_screen.py`, `render_resolved_batch3.py`, `verify_resolved_batch3.py`, scripts diagnósticos e de replay. São ferramentas operacionais de uma tentativa, **não interfaces de produção prontas para retomar cegamente**. Os helpers de renderização esperam uma conciliação completa que ainda não existe.

Para outro agente sem acesso à máquina: reconstruir fixtures sintéticas a partir desta descrição. Não solicitar nem carregar capturas reais em repositórios, issues, chats de grupo ou logs públicos.

## Verificação e segurança para o próximo agente

Offline, no checkout correto:

```bash
uv sync --locked --python 3.12
uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
```

Não executar extração live como parte automática da suíte.

Critérios de aceitação:

1. Regressão da coexistência real falha antes da correção e passa depois.
2. Tabela+instruções não é tratada como zero; paginação é coletada integralmente.
3. Ausência de tabela sem cartão completo não é convertida em zero.
4. Fonte vazia e mensal não zero continuam bloqueados.
5. Sessão fresca por aluno, identidade de formulário, guards HTTPS/host/path/redirect e ausência de bearer admin no painel permanecem.
6. Nenhuma linha malformada desaparece silenciosamente do denominador.
7. Totais/acertos por assunto reconciliam com mensal e são registros, não comprovação de execução.
8. Antes de retomar live, conferir autorização, ausência de processo concorrente, seleção exata, fonte da tentativa anterior e incerteza de POST. Usar novo run para bloqueado; não mutar antigos nem repetir os cinco válidos.
9. Parar no primeiro erro; somente depois de 31 fontes conciliadas excluir vazios e gerar PDFs padrão.
10. Geração não autoriza envio. Aprovação humana deve vincular o hash exato de um plano novo. Planos/aprovações antigos são imutáveis.

**Não desativar gates para terminar o lote. Não publicar dados de alunos ou credenciais. O responsável assumirá a inspeção/correção com outro agente.**
