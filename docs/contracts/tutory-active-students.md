# Contrato observado: alunos ativos da Tutory

Data da última verificação: 09/09/2026.

Este é um conector HTTP privado e monitorado, não uma API pública documentada pela Tutory.
O navegador é necessário somente para redescobrir o contrato quando a Tutory mudar. A execução
mensal e a renovação da sessão usam requisições HTTP diretas.

## Autenticação

- `POST /intent/login`
- Corpo `application/x-www-form-urlencoded`: `account`, `password`
- A resposta estabelece a sessão usada nas consultas HTML seguintes.
- A página autenticada fornece a autorização usada pela geração do Relatório do Coach.
- A ferramenta descobre essa autorização após o login; `TUTORY_API_TOKEN` fica apenas como opção
  de compatibilidade e não é necessário na configuração normal.

## Total esperado

- `GET /index`
- O total ativo aparece no texto do elemento `role="progressbar"`, antes do percentual.
- Esse indicador é a ocupação do plano e pode estar atrasado em relação aos cadastros.
- Em 09/09, mostrou 289 enquanto a busca de ativos e a lista paginada de coaching continham
  os mesmos 290 IDs. O registro adicional havia sido cadastrado no dia e aparecia ativo na
  ficha e na busca; não aparecia na busca de inativos. Não usar esse número como constante.

## Consulta

- `GET /alunos/consulta`
- Campos: `nome`, `status`, `curso`
- Status: vazio para todos, `ativos` para ativos e `desativados` para inativos.
- A resposta é HTML e contém no máximo 50 resultados.
- Cada registro usa `.pesquisa-aluno-container`, nome em `.pesquisa-aluno-nome` e ID Tutory em
  `form.form_visualizar_aluno input[name="id"]`.

Não foi encontrada paginação funcional. Parâmetros comuns de página e limite foram ignorados.

## Enumeração completa

1. Consultar `status=ativos` e ler as opções de `select[name="curso"]`.
2. Consultar `status=ativos&curso=<id>` para cada plano e deduplicar por ID Tutory.
3. Quando houver plano com 50 registros ou diferença do contador, consultar a seleção de
   coaching completa, descrita abaixo. Subdividir planos saturados com `nome=A` até `nome=Z`,
   unindo por ID, até obter exatamente os IDs da lista paginada. Não parar porque o contador
   atrasado foi alcançado.
4. Exigir igualdade dos conjuntos de IDs entre busca de ativos e seleção de coaching.
   Sem essa comprovação, bloquear antes de consultar telefones ou gerar relatórios. Quando
   as duas listas coincidem e apenas o painel diverge, registrar aviso com as contagens.
5. Para consultas sem saturação e com total correto, preservar a conferência direta anterior.

### Confirmação por paginação

- `GET /alunos/coaching` retorna a primeira página, sem filtro de curso.
- `.admin-pagination .page-link.active` identifica a página atual; o link `Última` declara
  a página terminal. Links observados: `?p=2&curso=0`, `?p=3&curso=0`.
- Cada linha de `tbody` tem um `input.relatorio-aluno-check[data-id]`.
- Cada página não terminal contém 100 alunos; a última contém até 100. Em 09/09 foram
  observados 100, 100 e 90, com 290 IDs únicos, iguais aos da busca explícita `status=ativos`.
- O adaptador exige metadados válidos, escopo sem filtro, página solicitada correta e número
  terminal estável. Páginas parciais, IDs vazios/duplicados, mudança do total de páginas,
  destinos externos e divergências de identidade são falhas de contrato.
- A consulta é limitada a 1.000 páginas por proteção operacional; atingir formato fora desse
  contrato bloqueia com erro, sem truncar silenciosamente. Não é limite por cliente.
- A lista de coaching não substitui a comprovação de status: os IDs precisam coincidir com
  a consulta de ativos. Nenhum aluno é acrescentado apenas para igualar um contador.

Na evidência de 25/08/2026 havia 73 planos e apenas um atingiu o limite de 50. Em 27/08/2026, o
login HTTP e a enumeração completa resultaram exatamente nos **279 alunos ativos** mostrados no
painel. Nenhum nome, telefone, matrícula, e-mail, cookie, senha ou token foi salvo neste documento.

## Telefone

- `GET /alunos/index?aid=<id Tutory>` usando a mesma sessão autenticada.
- DDD em `select[name="ddd"] option[selected]`.
- Número em `input[name="celular"]`.
- O HTML do Relatório de Desempenho atual não contém o telefone do aluno; o botão de WhatsApp
  apenas compartilha o link do relatório. Portanto, a ficha é a fonte verificada do destino.

## Geração do Relatório do Coach

- `POST /intent/cadastrar-relatorio-coach` com Bearer token.
- Corpo: `alunos[]`, `dt_ini`, `dt_fim`, `agrupamento=semana`.
- Datas obrigatoriamente em `DD/MM/AAAA`; o formato ISO foi rejeitado pela Tutory.
- Resposta: `data[]` com `id` e `token`, mais `result` booleano.
- Documento: `GET /documentos/relatorios/desempenho?key=<token>`.
