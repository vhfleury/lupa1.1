# Checklist antes do primeiro processo real

> **MINUTA para revisão de advogado; não é parecer jurídico.** Versão 0.1 · 21 de outubro de 2026 · subetapa 8.2.

Nenhum processo real entra antes de todos os itens marcados, com data e responsável.

| # | Item | Responsável | Feito em |
| --- | --- | --- | --- |
| 1 | Documentos desta pasta revisados por advogado e versão final aprovada por Victor | Victor | |
| 2 | Termos de uso aceitos por desembargador e cada assessor (`termos-de-uso.md`, seção 13) | usuários | |
| 3 | Aviso de tratamento entregue ao gabinete; encarregado e canal definidos | Victor | |
| 4 | Decisão do object storage assinada (`docs/decisoes/object-storage.md`) | Victor | |
| 5 | Chave da API da Anthropic do piloto criada e guardada fora do repositório | Victor | |
| 6 | Termos da API conferidos: vedação de treinamento, prazo de retenção, local de processamento; cópia e data guardadas | Victor + advogado | |
| 7 | Smoke test com o modelo real (testes `llm`) executado | Victor | |
| 8 | Vault em produção: TLS, unseal com partes guardadas, reinício testado (`operacao.md` 4.1, 4.6) | Victor | |
| 9 | Certificado real no proxy; porta direta da API e console do MinIO fechados (`operacao.md` 5) | Victor | |
| 10 | Backup agendado, expurgo agendado e uma restauração testada no ambiente do piloto | Victor | |
| 11 | Guias lidos por pelo menos um assessor, com dúvidas respondidas | desembargador | |
| 12 | Dados jurídicos confirmados pelo gabinete: calendários e feriados, prazos, tipos penais, regras de borda das validações | gabinete | |
| 13 | Processo escolhido confirmado como público (sem segredo de justiça em nenhuma peça) | desembargador | |
| 14 | Dados sintéticos removidos do ambiente do piloto, inclusive objetos órfãos | Victor | |
| 15 | Dois administradores nominais ou procedimento de contingência definido | Victor | |
| 16 | Forma de informar o tribunal combinada (art. 19, § 7º) | desembargador | |

Assinaturas: Victor ______ data ___ · Desembargador ______ data ___
