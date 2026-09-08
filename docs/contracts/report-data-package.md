# Contrato do pacote de dados do relatório

**Versão:** `1.0`

**Formato:** JSON Lines (`.jsonl`)
**Comando:** `kairos-report data export --run <id>`

## Objetivo

Entregar ao Hermes e ao gerador de PDF uma fonte única, validada e independente do layout.
Cada linha representa um aluno do ciclo, inclusive quando seus dados estão pendentes ou bloqueados.
Assim, a quantidade exportada nunca parece completa ocultando falhas individuais.

O resumo retornado pelo comando informa:

- `expected`: alunos esperados no ciclo;
- `exported`: registros efetivamente escritos;
- `complete`: verdadeiro somente quando as quantidades conferem e não existem dados bloqueados ou
  pendentes;
- `ready`, `blocked` e `pending`: situação acadêmica dos registros;
- `delivery_blocked`: alunos cujos dados estão disponíveis, mas a entrega não está liberada.

## Envelope por aluno

- `schema_version`: versão do contrato;
- `report_id`: identificação interna do relatório;
- `data_status`: `ready`, `blocked` ou `pending`;
- `delivery_status`: `ready` ou `blocked`;
- `issues.data`: problemas que impedem usar os dados;
- `issues.delivery`: problemas que impedem o futuro envio;
- `data`: ficha acadêmica completa quando `data_status=ready`; caso contrário, `null`.

O telefone não faz parte deste arquivo. Telefone inválido mantém os dados acadêmicos disponíveis e
marca apenas `delivery_status=blocked`.

### Validação temporal

Para exportação operacional pronta, as fontes de estudo e questões precisam conter evidência
diária validada para o mesmo início e fim do ciclo. Totais de cards acumulados não comprovam o
mês. Horas e dias estudados são calculados a partir da série diária; datas e somas são conferidas
antes da ficha pronta. A série de estudo cobre todos os dias do período, inclusive zeros.

Dados legados sem essa comprovação permanecem no banco para auditoria, mas sua exportação
operacional é bloqueada. Um novo ciclo precisa obter a evidência correta. A revisão antiga não
deve ser liberada simplesmente por ter status válido, aprovação ou PDF gravado anteriormente.

## Ficha acadêmica pronta

### Identificação

- nome do aluno;
- curso;
- início e fim do período;
- identificador interno do relatório.

### Resumo mensal

- horas estudadas;
- dias de estudo;
- dias sem estudo no período;
- média de horas por dia ativo;
- acerto geral;
- progresso do plano;
- percentual restante do plano.

### Evolução semanal

- rótulo da semana;
- horas realizadas;
- meta de horas;
- total de horas planejadas;
- aderência percentual à meta;
- diferença de horas entre a primeira e a última semana;
- tendência: `improving`, `stable`, `declining` ou `unavailable`.

A tendência só existe com pelo menos duas semanas. A aderência só existe quando a meta total é
maior que zero.

### Disciplinas e áreas

- matéria mais estudada;
- matéria menos estudada;
- ranking com tempo e acerto;
- progresso por disciplina;
- desempenho por área.

### Modalidades

- horas por modalidade;
- total de horas nas modalidades;
- participação percentual de cada modalidade.

### Questões e atividades

`questions` contém total, acertos, erros, taxa de acerto, série semanal, disciplinas e assuntos.
`student_activity` contém estudos e revisões detalhados quando fornecidos pela fonte.
Em registros legados essas fontes podem ser `null`: isso representa indisponibilidade, não zero;
esses registros não dispensam a validação temporal para uma nova exportação operacional pronta.
A série diária validada é normalizada em semanas de calendário; o PDF agrega essas semanas em
quatro grupos comuns sem perder totais. A evidência diária permanece nos dados persistidos.

## Métricas explicitamente indisponíveis

Enquanto a Tutory não fornecer evidência suficiente, o pacote marca:

- `active_days_by_week`;
- `accuracy_by_week`, somente quando a fonte de questões não está disponível;
- `most_improved_subject`.

Essas informações não podem ser inventadas pelo Hermes nem inferidas pelo layout.

## Informações deliberadamente excluídas

- telefone ou destino de WhatsApp;
- comparação com turma ou Top 10;
- média de outros alunos;
- credenciais, token, cookie ou HTML bruto;
- texto motivacional ou análise gerada por IA;
- qualquer decisão visual do PDF.

## Local padrão

```text
<KAIROS_DATA_DIR>/review/YYYY-MM/run-ID/report-data.jsonl
```

É possível informar outro destino com `--output`. A gravação substitui o arquivo somente depois de
todo o conteúdo estar pronto, reduzindo o risco de deixar uma exportação parcial após interrupção.

O arquivo contém nomes e dados acadêmicos reais. Ele deve permanecer no ambiente privado do cliente
e nunca ser adicionado ao Git.
