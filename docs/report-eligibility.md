# Elegibilidade dos relatórios

Por padrão, alunos com plano pausado no dia da geração ou com menos de 15 dias desde a
Data de Início da mentoria não participam da geração. Os dias são corridos, no fuso
`KAIROS_TIMEZONE` (padrão `America/Sao_Paulo`). Exatamente 15 dias permite participação.

O cadastro administrativo fornece `data_inicio`. O acesso autorizado ao painel do aluno
permite consultar o histórico de pausas. Início e fim da pausa são inclusivos; pausas
encerradas e futuras não excluem por si só. A consulta nunca cadastra, remove ou retoma pausas.
Aluno inativo e plano pausado continuam sendo condições diferentes.

Configuração:

```dotenv
KAIROS_REPORT_ELIGIBILITY_ENABLED=true
KAIROS_MENTORSHIP_MINIMUM_DAYS=15
KAIROS_TIMEZONE=America/Sao_Paulo
```

O filtro é habilitado mesmo se as duas primeiras variáveis não existirem. Alterar o mínimo
para zero desativa apenas a carência; pausas continuam bloqueadas. `false` desabilita
explicitamente a política inteira para instalações legadas que não a utilizam.

## Pontos de proteção

- `run extract`: verifica antes de criar o relatório na Tutory. A lista completa de alunos
  ativos continua sendo reconciliada antes do filtro. Registros excluídos ficam `blocked`,
  sem métricas nem PDF, preservando a seleção e o motivo para auditoria.
- `report generate-batch`: verifica novamente antes do PDF, protegendo dados antigos.
- `report generate-live`: verifica antes da extração de diagnóstico.
- `report generate --input`: exige correspondência com ID do relatório, nome e período no
  banco operacional e verifica a situação atual. Arquivo avulso sem identidade confirmada
  não permite pular a política.
- Manifesto de entrega, `delivery prepare` e `delivery submit`: consultam a situação atual.
  Um PDF antigo ou plano já aprovado não permite enviar para aluno que passou a estar pausado.
  Pedidos já aceitos pela fila do Runtime não são cancelados por este gerador.

Motivos privados: `mentorship_too_recent`, `study_plan_paused`, `eligibility_unverified`.
Se faltarem dados, o HTML mudar ou a consulta falhar, o aluno fica bloqueado para revisão.
O marcador explícito de nenhuma pausa é necessário; página vazia/login não libera o aluno.
Respostas Retry-After mantêm as proteções de pausa da extração.

`excluded` apresenta quantos foram excluídos pelas duas regras de negócio; `blocked`
continua incluindo esses registros para compatibilidade. Exclusões previstas não tornam
um lote incompleto; ausência de confirmação continua sendo bloqueio de conferência.
Os motivos aparecem em `validation_errors`, nos itens do manifesto e em
`eligibility_exclusions` da geração. Não reutilize uma extração bloqueada como se fosse
um novo ciclo: um novo ciclo consulta a situação novamente.

Não há migração de banco nem alteração do canal, dos templates, das aprovações ou do Runtime.
As novas consultas utilizam o mesmo espaçamento e tentativas limitadas do cliente Tutory.
As credenciais e campos privados do acesso ao painel nunca devem aparecer em logs.
