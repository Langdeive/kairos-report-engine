# Aprovação e integridade no envio pelo Runtime

O hash é uma impressão digital do plano e do PDF. Deve ser mantido nos dois modos: permite detectar alterações e vincular recibos ao plano correto. Gerar um hash não exige aprovação humana.

- `KAIROS_APPROVAL_MODE=required` (padrão): `delivery submit` exige `--approved-hash` correspondente ao plano preparado.
- `KAIROS_APPROVAL_MODE=automatic`: `delivery submit` não exige aprovação humana. O Hermes ainda precisa preparar o plano e chamar explicitamente o comando de envio.

Em ambos os modos permanecem: verificação de aluno/destinatário/período, elegibilidade (pausas e mínimo de dias), dados e arquivo atuais, versão do template, hash do PDF e idempotência das solicitações. Uma falha de integridade deve interromper o processo, não ser contornada por aprovação automática.

Para um futuro cron, selecionar o período e os alunos, extrair, validar, gerar PDFs, preparar as decisões de template e submeter o plano. Persistir plano e recibos e reutilizar o mesmo plano ao recuperar uma submissão incerta. Não criar outro plano para tentar novamente um envio cujo resultado é desconhecido. Impedir execuções simultâneas do mesmo lote. Monitorar os estados do Runtime: registro na fila não comprova entrega.

Esta correção não cria cron, não altera o `.env` operacional e não ativa envios automáticos. O modo automático já existia; foi revisado com testes adicionais de integridade e recuperação de submissão incerta. A automação completa do lote e sua política de seleção são uma etapa operacional separada.
