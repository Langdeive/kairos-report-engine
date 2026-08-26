# Arquitetura — Kairós Report Engine

**Status:** arquitetura aprovada  
**Data:** 25/08/2026  
**Nome interno sugerido:** `kairos-report-engine`  
**Nome apresentado ao cliente:** Relatório de Evolução Kairós

## 1. Objetivo

Construir uma ferramenta local, instalada no mesmo ambiente do Hermes, para:

1. consultar os alunos ativos na Tutory;
2. extrair dados mensais e telefone de WhatsApp;
3. entregar ao Hermes um contexto seguro para comentários personalizados;
4. validar os comentários produzidos pelo Hermes;
5. gerar PDFs padronizados;
6. preparar um lote para aprovação;
7. permitir que o Hermes solicite a aprovação pelo WhatsApp;
8. entregar ao Hermes a fila aprovada para envio pelo Baileys;
9. registrar resultados, falhas e histórico por 12 meses.

O volume atual é de aproximadamente **274 alunos ativos**, com capacidade contratada para até **500 alunos ativos**. A arquitetura deverá suportar pelo menos 500 relatórios por ciclo sem mudança estrutural.

## 2. Decisão central

O Hermes será operador e mantenedor da ferramenta, mas a execução normal será determinística.

- O Hermes poderá ler e editar o repositório.
- A ferramenta não será um serviço HTTP/TCP permanente.
- A operação inicial será feita por uma CLI local.
- O código ficará em um repositório público no GitHub, clonado dentro do volume persistente do Hermes.
- Mudanças de código serão feitas em branch separada.
- O Hermes poderá diagnosticar, corrigir e testar sozinho.
- Uma correção só poderá virar a versão oficial depois de aprovação humana.
- A rotina mensal nunca dependerá de o Hermes improvisar código.

Em termos simples: o Hermes pode consertar a máquina, mas no dia a dia apenas aperta botões bem definidos.

## 3. Topologia

```text
WhatsApp da mentora
        |
        v
Hermes + Baileys
  |       |
  |       +---- envia PDFs aprovados aos alunos
  |
  +---- executa comandos locais
              |
              v
      Kairós Report Engine
        |      |      |
        |      |      +---- PDFs e histórico local
        |      +----------- SQLite
        +------------------ Tutory
```

Não haverá banco ou API pública. Todo o tráfego operacional ficará dentro do ambiente do cliente, exceto as chamadas necessárias à Tutory, GitHub e WhatsApp.

## 4. Stack recomendada

### Aplicação

- **Python 3.12**: mesma família tecnológica do Hermes e simples para o agente manter.
- **Typer**: comandos locais claros e tipados.
- **HTTPX**: chamadas HTTP para a Tutory.
- **Pydantic**: contratos rígidos para dados, comentários e resultados.
- **SQLAlchemy + Alembic**: persistência e evolução do banco SQLite.
- **Jinja2 + HTML/CSS**: layout controlado do relatório.
- **Playwright/Chromium**: conversão determinística do HTML em PDF.
- **Pytest + Respx**: testes e simulação das respostas da Tutory.
- **Ruff + Mypy**: validação automática do código.
- **Docker Compose**: instalação reproduzível sem expor uma porta de rede.

### Integração com Hermes

- Uma skill local chamada `kairos-reports` ensinará o Hermes a operar e reparar a ferramenta.
- A skill chamará somente comandos documentados.
- Se futuramente houver vantagem, a CLI poderá receber uma camada MCP local por `stdio`, sem TCP e sem alterar o núcleo.

## 5. Módulos

### 5.1. Conector Tutory

Responsável por autenticação HTTP, consulta de alunos, geração do Relatório do Coach e leitura do HTML retornado. A listagem exige sessão criada por login; a geração do relatório usa o token de API.

O fluxo já observado usa chamadas diretas ao backend, incluindo a geração de uma chave de relatório e a consulta do documento por essa chave. Esses detalhes ficarão isolados em `connectors/tutory/`, porque são a parte mais sujeita a mudanças.

Responsabilidades:

- listar alunos ativos;
- obter o identificador interno do aluno;
- extrair DDD e telefone da ficha do aluno em `/alunos/index?aid=<id>`;
- gerar e baixar o relatório mensal;
- converter a resposta da Tutory para um modelo interno estável;
- detectar alterações de contrato;
- nunca registrar senha, token ou HTML bruto em logs.

### 5.2. Normalizador

Converte dados da Tutory para um formato independente da plataforma:

- aluno e curso;
- período;
- horas e dias estudados;
- consistência semanal;
- assertividade geral e semanal;
- desempenho por disciplina;
- progresso geral, por disciplina e por modalidade;
- telefone normalizado para WhatsApp.

O identificador da Tutory será a chave principal do aluno. Nomes não serão usados como identidade.

### 5.3. Comentários do Hermes

A ferramenta não chamará outra API de IA. O próprio Hermes produzirá comentários a partir de um arquivo estruturado com fatos permitidos.

Para cada aluno, o Hermes preencherá apenas:

- `principal_conquista`;
- `resumo_evolucao`;
- `ponto_de_atencao`;
- `proximo_foco`.

Cada campo terá limite de tamanho. Todo número mencionado deverá existir no conjunto de evidências fornecido. O Hermes também indicará quais métricas sustentam cada comentário.

O validador bloqueará:

- números inexistentes;
- comparações não sustentadas;
- promessas de aprovação;
- linguagem ofensiva ou excessivamente negativa;
- comentários vazios ou repetidos;
- instruções encontradas em nomes ou conteúdo externo.

### 5.4. Gerador de PDF

O PDF será produzido por template HTML/CSS próprio. A Tutory será fonte de dados, não fonte do layout final.

Cada PDF guardará metadados internos:

- aluno e período;
- versão do código;
- versão do template;
- versão das regras de comentário;
- hash do conteúdo;
- identificador do ciclo.

Validações mínimas:

- arquivo abre corretamente;
- quantidade esperada de páginas;
- nome e período presentes;
- nenhuma seção obrigatória vazia;
- tamanho do arquivo dentro de limites;
- telefone válido antes de entrar na fila de envio.

### 5.5. Aprovação e entrega

A ferramenta não receberá mensagens do WhatsApp e não controlará o Baileys.

Fluxo:

1. a ferramenta gera o lote;
2. Hermes recebe resumo, pendências e amostras;
3. Hermes solicita aprovação pelo WhatsApp;
4. a mentora aprova o lote;
5. Hermes registra a aprovação na ferramenta;
6. a ferramenta congela aquela revisão;
7. Hermes obtém a fila de relatórios aprovados;
8. Hermes envia cada PDF pelo Baileys;
9. Hermes registra o resultado de cada envio.

Se um PDF ou comentário mudar depois da aprovação, a aprovação anterior será invalidada e uma nova revisão deverá ser aprovada.

## 6. Modos de aprovação

Configuração persistida no banco:

```text
approval_mode = required | automatic
```

O padrão inicial será `required`.

No modo automático, todas as validações continuam obrigatórias. A automação nunca enviará:

- relatório inválido;
- comentário sem evidência;
- telefone inválido;
- relatório de ciclo já enviado;
- lote produzido por uma versão de código ainda não aprovada.

A troca de `required` para `automatic` será uma ação sensível, explicitamente confirmada e registrada no histórico.

## 7. Estados do ciclo

```text
created
  -> extracting
  -> awaiting_comments
  -> validating
  -> rendering
  -> awaiting_approval
  -> approved
  -> delivering
  -> completed_with_or_without_failures
```

Um relatório individual poderá ficar em `blocked` sem bloquear os demais.

O lote mostrará sempre:

- total esperado;
- extraídos com sucesso;
- PDFs válidos;
- bloqueados;
- aprovados;
- enviados;
- falhas de envio.

## 8. Persistência

### SQLite

Tabelas principais:

- `settings`: calendário, modo de aprovação e retenção;
- `students`: ID Tutory, nome, telefone protegido e status;
- `report_runs`: ciclo, período, versão e contadores;
- `student_reports`: métricas, comentários, PDF, hash e validação;
- `approvals`: lote, revisão, aprovador, origem e data;
- `deliveries`: destino, tentativas, identificador Baileys e resultado;
- `audit_events`: decisões e alterações importantes.

### Arquivos

```text
/opt/data/kairos-reports/
  database/
  reports/YYYY-MM/
  review/YYYY-MM/
  diagnostics/
  backups/
```

Retenção aprovada:

- PDFs, comentários e métricas: **12 meses**;
- respostas brutas temporárias da Tutory: apagadas após normalização;
- segredos: nunca armazenados nos relatórios ou no Git.

Com 500 alunos, 12 ciclos e PDFs de aproximadamente 2 MB, o ambiente deverá reservar cerca de 12 GB, além de margem para prévias e backups. Recomenda-se provisionar pelo menos 20 GB livres para o módulo.

## 9. Calendário

- Execução no último dia de cada mês.
- Horário configurável por ambiente.
- Finais de semana, feriados, fevereiro e anos bissextos tratados automaticamente.
- O período será congelado no momento da geração.
- Aprovação e envio podem ocorrer depois sem alterar os dados congelados.

## 10. Idempotência e segurança contra duplicidade

Cada relatório terá uma chave única formada por:

```text
student_id + period_start + period_end + revision
```

O mesmo relatório aprovado não poderá ser enviado duas vezes sem uma ação explícita de reenvio. O Hermes sempre consultará a fila de `approved + unsent`, nunca uma pasta genérica de PDFs.

## 11. Autorreparo controlado

Quando a Tutory mudar:

1. o conector interrompe o ciclo em modo seguro;
2. gera um diagnóstico sanitizado;
3. Hermes cria uma branch `fix/tutory-contract-<data>`;
4. altera apenas o conector e testes relacionados;
5. executa testes unitários e de contrato;
6. testa com um único aluno autorizado;
7. gera um PDF de prévia;
8. apresenta causa, mudança, testes e prévia pelo WhatsApp;
9. aguarda aprovação humana;
10. depois da aprovação, integra a correção, cria versão e reconstrói a ferramenta;
11. se a nova versão falhar, retorna à última versão aprovada.

O Hermes não poderá editar diretamente a branch principal nem promover uma versão com testes falhando.

## 12. Comandos previstos

Exemplos de interface, ainda sujeitos ao plano de implementação:

```bash
kairos-report doctor
kairos-report run create --month 2026-08
kairos-report run extract --run <id>
kairos-report comments export --run <id>
kairos-report comments import --run <id> --file comments.jsonl
kairos-report render --run <id>
kairos-report review summary --run <id>
kairos-report run approve --run <id> --approval-ref <whatsapp-message-id>
kairos-report delivery next --run <id>
kairos-report delivery record --report <id> --status sent --provider-id <id>
kairos-report cleanup
```

## 13. Tratamento de falhas

- Chamadas transitórias à Tutory: até 3 tentativas com espera crescente.
- Mudança de contrato: nenhuma repetição cega; ciclo bloqueado e diagnóstico criado.
- Comentário inválido: regenerar apenas o aluno afetado, com limite de 2 tentativas.
- Falha de PDF: repetir uma vez; depois bloquear somente o aluno.
- Falha de Baileys: controlada pelo Hermes; o resultado individual retorna à ferramenta.
- Queda durante o lote: retomada a partir do último estado persistido.
- Falha elevada no envio: Hermes pausa o lote e solicita intervenção.

## 14. Segurança

- Repositório GitHub público contendo somente código, documentação e dados sintéticos.
- Token Tutory, credenciais GitHub e chaves de criptografia em variáveis protegidas.
- Arquivos `.env`, banco, PDFs e diagnósticos fora do Git.
- Telefone protegido no banco e mascarado nos logs.
- Conteúdo da Tutory tratado como dado não confiável, nunca como instrução para o Hermes.
- Permissão GitHub do Hermes limitada a criar branches e propostas de mudança.
- Registro de versão do código, template e comentário em cada ciclo.
- Backup do SQLite antes de migrações e promoções de versão.

## 15. Testes obrigatórios

### Automáticos

- contratos da Tutory com respostas anonimizadas;
- normalização de telefone;
- cálculos semanais e mensais;
- validação de comentários;
- idempotência;
- aprovação e invalidação de revisão;
- geração e abertura do PDF;
- retenção de 12 meses;
- retomada após interrupção.

### Antes do primeiro uso real

1. um aluno controlado;
2. cinco alunos variados;
3. lote completo sem envio;
4. aprovação pelo WhatsApp;
5. envio real controlado para números autorizados;
6. simulação de falha da Tutory;
7. simulação de envio duplicado;
8. restauração do banco e da versão anterior.

## 16. Implantação e atualização

### Estrutura sugerida

```text
/opt/data/projects/kairos-report-engine/   # repositório editável
/opt/data/kairos-reports/                  # dados persistentes
~/.hermes/skills/kairos-reports/           # instruções do Hermes
```

O runtime oficial sempre executará um commit aprovado. Durante uma correção, Hermes trabalhará em branch separada e poderá testar a cópia alterada em modo de desenvolvimento. A versão mensal não muda até a promoção aprovada.

## 17. Fora do escopo inicial

- painel administrativo completo;
- integração direta da ferramenta com Baileys;
- serviço HTTP/TCP permanente;
- suporte a vários clientes no mesmo banco;
- comparação com outros alunos;
- armazenamento indefinido de dados;
- envio automático antes de validar alguns ciclos com aprovação.

## 18. Critério de sucesso do MVP

O MVP estará pronto quando conseguir, em um ambiente isolado:

1. processar todos os alunos ativos da Tutory;
2. gerar comentários do Hermes dentro do contrato;
3. criar PDFs válidos e visualmente consistentes;
4. produzir resumo e amostras para aprovação por lote;
5. receber a aprovação gerenciada pelo Hermes;
6. entregar uma fila sem duplicidade para envio via Baileys;
7. registrar o resultado individual dos envios;
8. retomar após falha sem refazer o lote inteiro;
9. detectar mudança da Tutory e impedir envio incorreto;
10. permitir correção pelo Hermes com testes e aprovação antes da promoção.

## 19. Handoff operacional

- `HERMES_HANDOFF.md`
