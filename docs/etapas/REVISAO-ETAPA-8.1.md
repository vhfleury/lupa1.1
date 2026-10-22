# Revisão — Subetapa 8.1 (ambiente de piloto)

21 de outubro de 2026 · revisor

## 1. Verificação executada

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q   -> válido
portas publicadas no perfil de produção                                    -> só 443 e 80 (proxy)
curl /api/saude                                 -> {"api":"ok","db":"ok","minio":"ok","cofre":"ok"} 200
docker compose restart vault; vault status      -> Sealed true
curl /api/saude                                 -> {"...","cofre":"falha"} 503
scripts/vault_inicializar.sh --so-unseal        -> unseal ok; /api/saude 200; stack toda healthy
scripts/validar_caddyfile.sh                    -> modos acme e fornecido válidos (interno em uso)
scripts/conferir_piloto.py (no host)            -> 10 atendidos, 5 pendentes, 2 manuais
docs/imagens/grafana.png                        -> painel com cofre, fila, jobs por estado, falhas,
                                                   chamadas e tokens do modelo, auditoria por ação
scripts/verificar.sh                            -> ver seção 1.1
```

O achado da revisão 7.10 está corrigido e provado: com o cofre selado, a rota de saúde responde 503 e o healthcheck do Vault sai de `healthy`.

## 1.1 Verificação do backend

Executada pelo revisor: ruff e mypy limpos; 867 testes passaram, 3 pulados, 3 desmarcados; cobertura 98,28%; ponta a ponta da ingestão (1), regressão de injeção (2), front, cabeçalhos (4 rotas) e suíte do agente (9) verdes. Código de saída 0.

## 2. Critérios de saída

| Item | Resultado | Evidência |
| --- | --- | --- |
| Cofre selado detectado | ok | healthcheck por `vault status`; `/saude` com componente `cofre` cifrando e decifrando pela chave `lupa-saude`; prova acima; 4 testes novos |
| Perfil de produção | ok | só o proxy publica portas; `restart: unless-stopped`, limites de CPU e memória, rotação de logs, `read_only` onde possível, Vault com `IPC_LOCK` e mlock, volumes em `LUPA_DADOS_DIR`, backup e expurgo agendados pelo crond da própria imagem de backup (sem socket do Docker a um agendador) |
| Certificado e domínio | ok | `LUPA_TLS_MODO` com `interno`, `acme` e `fornecido`; os modos de produção só aceitam TLS 1.3 e enviam HSTS; validados com `caddy validate` |
| Vault de produção | ok no que é possível sem KMS | 3 partes com limiar 2 em modo produção, cada parte exibida uma vez sem gravar em disco; token raiz revogado; backup do Vault incluído no `.age` diário com opção de cópia fria; restauração testada no dev (44 chaves Transit iguais) |
| Monitoramento | ok | Prometheus e Grafana fixados por digest, só em loopback, segredos por arquivo; rota `GET /metricas/servico` com token Bearer (404 sem token configurado, 401 com token errado); 4 regras de alerta aprovadas pelo `promtool`; painel provisionado e capturado |
| Instalação e conferência | ok | `instalar_piloto.sh/.ps1` idempotentes com confirmação; `conferir_piloto.py` confere o checklist da seção 12 contra o ambiente |

Contagens: backend de 860 para 867 testes; E2E 36.

## 3. Decisões do executor endossadas

- Sem TLS entre API/worker e Vault no piloto: um host, redes internas sem porta publicada; quem observa a rede do Docker já é root. Registrado em `docs/operacao.md` 4.6 e a reavaliar se o Vault sair do host.
- HSTS mantido no modo de desenvolvimento porque a varredura de cabeçalhos e o E2E exigem; sem efeito com certificado não confiável.
- Agendador pelo crond da imagem de backup, para não entregar o socket do Docker a um serviço de agendamento.
- `/metricas/servico` separado da rota de admin, porque o Prometheus não faz login com TOTP.

## 4. Decisão

**Aprovado.** O que agentes conseguem construir para a primeira versão está concluído.

## 5. Pendências que só o ambiente real resolve (8.3 em diante)

1. Nada rodou num servidor real: ACME, certificado fornecido, perfil de produção com volumes em outro disco, `instalar_piloto.sh` ponta a ponta (precisa de terminal interativo e `sudo`), Vault com três pessoas segurando as partes.
2. Sem auto-unseal (não há KMS) e sem envio de notificação dos alertas; os alertas existem no Prometheus, falta um canal.
3. `conferir_piloto.py` precisa do CLI do Docker e por isso roda no host, não no contêiner da API; o manual deve dizer isso explicitamente.
4. No ambiente de desenvolvimento permanecem, por decisão ou por natureza do dev: TLS 1.2 aceito no modo interno, portas da API e do console do MinIO em loopback, Vault com uma parte, backup agendado só no perfil de produção, 344 objetos órfãos em claro, termos do fornecedor do modelo a conferir.
5. Ficou em `.backups/` o arquivo do teste de backup (830 KB); apagar com o expurgo ou à mão.
