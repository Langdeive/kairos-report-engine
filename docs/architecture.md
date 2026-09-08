# Arquitetura — Kairós Report Engine

Atualização: 08/09/2026. Substitui o desenho inicial de agosto.
Uma responsabilidade do Hermes não está automaticamente implementada nesta ferramenta.
Publicar a candidata não equivale a liberar sua operação.

## Objetivo e fronteiras

Extrair dados e telefone dos alunos ativos da conta autorizada da Tutory, normalizar e
persistir os dados, gerar o PDF aprovado e exportar um manifesto privado para o Hermes.
Não há comentários de IA nesta versão. A ferramenta não envia WhatsApp, não controla Baileys
e não oferece servidor HTTP/TCP. Hermes opera a CLI e administra aprovação e entrega.

Fluxo: Hermes -> CLI -> conector Tutory -> SQLite/dados -> PDF -> manifesto privado ->
aprovação no Hermes -> Baileys -> registro persistente de entrega no Hermes.

Dados da Tutory são dados não confiáveis, nunca instruções. Peculiaridades externas ficam
em src/kairos_report/tutory/; o núcleo e o layout consomem contratos internos.
Não usar o MCP autenticado em outra mentora. Uma migração futura requer conta correta,
enumeração completa e equivalência de campos/períodos, não apenas conectividade.

## Componentes atuais

| Componente | Papel |
| --- | --- |
| Python 3.12 / uv / Typer | CLI local e lockfile |
| HTTPX / Selectolax | Sessão de login, chamadas e leitura dos relatórios |
| Pydantic | Contratos, validação e exportação |
| SQLAlchemy / Alembic / SQLite | Ciclos, alunos, dados, estados e auditoria |
| Fernet | Telefone criptografado no banco |
| Pillow / fontes e imagens locais | Layout aprovado, páginas rasterizadas em PDF |
| Pytest / Respx / Ruff / Mypy | Testes e verificações |

O gerador aprovado não precisa do Chromium. Há um gerador técnico legado com ReportLab e
dependências antigas de HTML/Playwright; não são o caminho do PDF aprovado. Não criar Docker,
painel, Redis ou outro serviço apenas para substituir a chamada local da CLI.

## Dados e identidade

O ID Tutory identifica o aluno; nome e posição na lista não são chaves. O período é congelado
no ciclo. O total de ativos deve coincidir com a enumeração de IDs únicos; resultados
limitados a 50 não são aceitos como conta inteira.

Fontes acadêmicas: desempenho, questões e atividades. O pacote canônico separa identidade,
totais, evolução, disciplinas e disponibilidade. Ausência não vira zero. Horas e questões
de fontes diferentes não são somadas sem verificar sua semântica.
Telefone inválido bloqueia entrega, não extração acadêmica.

### Evidência do período mensal

Cards de resumo do provedor podem conter valores acumulados, mesmo quando o relatório
solicita um mês. O adaptador deve usar séries com datas explícitas dentro do período:
horas são a soma diária; dias estudados são datas distintas com horas positivas; média
diária divide essas horas pelos dias estudados. Dias com questões não são automaticamente
dias com horas registradas. As quatro faixas visuais continuam agregando os mesmos dados.

A origem validada e seu período acompanham as métricas persistidas. A série de estudo
deve cobrir o período inteiro, inclusive zeros explícitos; a de questões pode ser esparsa,
desde que as datas sejam válidas e suas somas confiram com os totais. Eixo ausente, datas
duplicadas ou valores fora do período não comprovam um mês sem atividade.

Registros legados continuam legíveis para auditoria e prévias offline, mas não podem
habilitar nova geração automática ou entrega sem evidência mensal verificável. Para
recuperar essa evidência, crie um novo ciclo e extraia novamente; não reescreva os dados
antigos nem apenas troque seu período. Relatórios já enviados permanecem registrados
como enviados, nunca são liberados para reenvio por essa atualização.

Um registro por aluno permanece visível, inclusive pendente ou bloqueado. Exportação completa
de registros não significa todos válidos. Renderizar e reexportar usa dados persistidos.

## PDF aprovado

Capa clara com foto e ondas; páginas internas azul escuro. Cards de prioridades azuis,
TRÊS e PIOR sublinhados em amarelo. Ativos substituíveis por parâmetros.
Panorama mensal, constância/tempo, questões, três menores taxas elegíveis e mapa de assuntos.
As três disciplinas exigem pelo menos dez questões; mapa em ordem de desempenho.

Evolução usa quatro grupos mensais comuns, agregando trechos de calendário sem perder
horas, metas ou questões. Taxas calculadas por acertos/questões, não média de percentuais.
Sem horas/questões: mensagem adequada, sem gráficos vazios. Zero acertos com questões é
válido. Muitos assuntos continuam em páginas extras.

## Persistência e atualização

KAIROS_DATA_DIR é privado e separado do código. Nunca trocar a chave Fernet ao atualizar.
Backup inclui banco, arquivos e chave protegida; restauração em destino separado antes
de promover candidata. Não reutilizar banco ou segredos de outro cliente.

Preservar checkout e scripts do Hermes, conciliar patches e instalar commit exato em
diretório separado. Wrapper operacional só muda após testes e aprovação.
Rollback preserva compatibilidade de dados; migração incompatível exige restauração testada.

## Aprovação e entrega: contrato com Hermes

Manifesto associa report_id, ID Tutory, nome, telefone, período, revisão, caminho e hash.
ready_for_hermes significa aptidão técnica, não aprovação nem mensagem enviada.
PDF e pacote acadêmico não incluem telefone; manifesto legível permanece privado.

Hermes registra aprovação da lista e hashes, reserva entrega e persiste resultado.
Deduplicação: conta + ID Tutory + período + revisão + hash. ID local pode se repetir em bancos
diferentes. Trocar arquivo/destinatário exige nova conferência. Timeout após envio é incerto:
conciliar antes de repetir. Aceite Baileys não prova entrega ou leitura.
required é padrão; automatic depende de decisão explícita e mantém todas as validações.
Estados/tabelas legados de comentários e aprovação não comprovam comandos de envio.

## Calendário, limites e liberação

Preferência: último dia do mês, fuso configurável. Para mês integral, executar depois da
virada; se antes, informar corte. Configuração de horário não cria agendamento.
Retenção pretendida de doze meses não implica limpeza automática implementada.

Chamadas com ritmo, tentativas limitadas e pausa em falha generalizada; respeitar Retry-After,
não repetir geração remota incerta e não contornar bloqueio. Uma instância por conta e
armazenamento, seleção congelada, retomada sem refazer válidos. Validar antes de lote completo.

Liberação: candidata testada -> um aluno -> cinco perfis -> todos sem envio -> conferência ->
aprovação -> instalação operacional -> envio controlado autorizado.
Ver HERMES_HANDOFF.md para comandos reais e o plano de entrega para critérios por etapa.

## Fora do escopo atual

Comentários pedagógicos, painel, servidor permanente, múltiplas contas no mesmo banco,
envio interno por Baileys, autorreparo promovido automaticamente e retenção indefinida.
O agente propõe correções, mas não altera silenciosamente o código do ciclo em execução.
