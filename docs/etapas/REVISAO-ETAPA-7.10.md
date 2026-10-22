# Revisão — Subetapa 7.10 (documentação de operação, ensaios e itens herdados)

21 de outubro de 2026 · revisor

## 1. Verificação executada

- `scripts/recifrar_objetos_legado.py` em modo de simulação, após a execução do executor: 0 objetos em claro pertencentes a processos existentes; 344 objetos em claro de processos que já não existem no banco (removidos pela limpeza da 6.10), sem chave para recifrar, não tocados.
- `docs/operacao.md` com 13 seções: pré-requisitos e dimensionamento, instalação do zero, atualização, Vault, certificado e portas, backup e restauração, descarte e rotação, dados sintéticos, monitoramento, resposta a incidente, relatório de uso, checklist de segurança da seção 6 dos requisitos com estado em 21/10/2026, e o registro dos ensaios.
- `.gitattributes` com LF para scripts, configuração, documentação e código do front; binários marcados.
- Evento `identidade_lida` passou a registrar `usuario_id` (os 36 eventos anteriores à correção continuam sem, como esperado; dois testes novos cobrem os novos).
- Vault aberto, `/saude` 200, 116 GB livres.
- `scripts/verificar.sh` completo: ver seção 1.1.

## 1.1 Verificação do backend

Executada pelo revisor: ruff e mypy limpos; 860 testes passaram, 3 pulados, 3 desmarcados; cobertura 98,27%; ponta a ponta da ingestão (1), regressão de injeção (2, recall 1,0), front, cabeçalhos (4 rotas) e suíte do agente (9) verdes. Código de saída 0.

## 2. Critérios de saída

| Item | Resultado | Evidência |
| --- | --- | --- |
| Manual de operação | ok | `docs/operacao.md`, 13 seções, inclusive a sequência de recuperação do incidente de disco cheio desta etapa |
| Ensaio de credencial comprometida | ok | rotação da chave do gabinete pela rota (envelope `vault:v1` para `v2`, 1 DEK rewrapada), reset de senha revogando sessões, reset de MFA; sessões legítima e invasora com 401; dossiê abre após rotação; auditoria com `chave_rotacionada`, `senha_resetada`, `mfa_resetado` |
| Ensaio de injeção | ok | resposta bloqueada, processo `em_revisao`, pergunta seguinte recusada, liberação pelo desembargador, chat volta; auditoria com `chamada_modelo` bloqueado, `processo_em_revisao`, `revisao_liberada` |
| Ensaio de reinício do Vault | ok | 15,9 s do reinício à confirmação; selado, dossiê responde 500; após unseal, API e worker decifram sem reinício |
| `identidade_lida` com `usuario_id` | ok | três chamadores ajustados em uma linha cada; dois testes |
| Teste de recusa do backup por falta de espaço | ok | `LUPA_BACKUP_ESTIMATIVA_BYTES` força a conferência; `tests/backup/test_espaco.py` |
| `.gitattributes` e `preparar_repositorio.md` | ok | conferidos |
| Recifragem dos objetos legados | ok | 4 objetos (2 processos, 525 MB) em 40,6 s; segunda execução não encontra nada; idempotente |

## 3. Achado do ensaio que precisa de correção na Etapa 8

O compose marca o serviço `vault` como saudável mesmo selado, e `GET /saude` não consulta o Vault. Com o cofre selado, a API responde 200 em `/saude` e 500 em qualquer rota que decifre. Corrigir em 8.1: healthcheck do Vault por `vault status` exigindo `Sealed false`, e `/saude` com componente `cofre`. Até lá, o manual instrui a conferir o unseal após qualquer reinício.

## 4. Decisão

**Aprovado.** Etapa 7 concluída.

## 5. Decisões e pendências para Victor antes do piloto

1. **344 objetos órfãos em claro no storage de desenvolvimento**, de processos sintéticos já removidos do banco. Não há chave para recifrá-los e a exclusão é irreversível, por isso o executor não apagou. Recomendação: apagar antes do piloto; são só dados sintéticos. O script de descarte não os alcança porque não há processo; basta um `mc rm` ou um pequeno script com lista por prefixo.
2. **Vault em produção**: TLS, auto-unseal ou divisão das partes de unseal entre pessoas, backup frio do volume (o Vault usa storage em arquivo, então `raft snapshot` não se aplica). Tudo documentado como pendente para 8.1.
3. **Certificado real no proxy** e porta direta da API não publicada (8.1).
4. **Prazos de comunicação de incidente**: o manual não cita artigos nem prazos porque `requisitos-v1.md` não os fixa; manda avisar Victor e o desembargador no mesmo dia e remete aos documentos de conformidade da 8.2.
5. Assinatura da decisão do object storage (`docs/decisoes/object-storage.md`).
