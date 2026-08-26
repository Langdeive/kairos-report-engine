# Contrato observado: alunos ativos da Tutory

Data da verificação: 25/08/2026.

Este é um conector HTTP privado e monitorado, não uma API pública documentada pela Tutory.
O navegador é necessário somente para descoberta ou renovação excepcional; a execução mensal usa
requisições HTTP diretas.

## Autenticação

- `POST /intent/login`
- Corpo `application/x-www-form-urlencoded`: `account`, `password`
- A resposta estabelece a sessão usada nas consultas HTML seguintes.
- O token de API permanece necessário para a geração do Relatório do Coach, mas sozinho não
  autentica `GET /alunos/consulta`.

## Total esperado

- `GET /index`
- O total ativo aparece no texto do elemento `role="progressbar"`, antes do percentual.
- Na verificação, o painel mostrou **274 alunos ativos** de uma capacidade de 500.

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
3. Quando um plano retornar exatamente 50 registros, subdividir esse plano com `nome=A` até
   `nome=Z`, unindo novamente por ID.
4. Comparar o total deduplicado com o contador de ativos do painel e falhar de forma segura se
   houver qualquer diferença.

Na evidência de 25/08/2026 havia 73 planos, apenas um atingiu o limite de 50 e a união final
resultou exatamente nos **274 alunos ativos**. Nenhum nome, telefone, matrícula, e-mail, cookie,
senha ou token foi salvo neste documento.

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
