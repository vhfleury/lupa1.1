# Lupa — Roteiro do piloto (o que Victor faz agora)

22 de outubro de 2026 · revisor

Tudo que agentes constroem para a primeira versão está pronto (Etapas 0 a 7, 8.1 e 8.2). Este roteiro ordena o que depende de você e do gabinete. Cada passo diz quem faz, o que usar, e como saber que terminou. "Agente" marca o que ainda pode ser delegado a um agente Opus com minha revisão; o resto é seu ou do gabinete.

Documentos que o roteiro usa: `docs/operacao.md` (manual do operador), `docs/conformidade/checklist-piloto.md` (16 itens), `docs/calibracao-projudi.md` (primeiro processo real), `docs/guia-assessor.md` e `docs/guia-desembargador.md`, `docs/etapas/CONFORMIDADE-GERAL.md` (estado e decisões).

---

## Fase 0 — Decisões antes de tocar em servidor (1 a 2 semanas, em paralelo)

| # | Decisão | Quem | Como | Pronto quando |
| --- | --- | --- | --- | --- |
| 0.1 | Pseudonimização de vítimas e testemunhas | Você decide; agente implementa | Opção A (recomendada): estender `reu_identidade` a uma tabela de identidades por papel (réu, vítima, testemunha), extraída da denúncia, dos termos de depoimento e das certidões; medir recall nos sintéticos; teste de que nenhum nome cadastrado chega ao modelo. Opção B: aceitar e registrar no aviso de tratamento | A: suíte verde e revisão aprovada. B: aviso alterado e assinado |
| 0.2 | Chave da API da Anthropic e termos | Você | Criar a chave na conta da Anthropic; ler os termos vigentes da API quanto a treinamento, retenção e local de processamento e guardar cópia datada em `docs/conformidade/`; rodar no seu computador o smoke real: `pytest -m llm --no-cov --noconftest tests/agente/test_smoke_llm.py` com `ANTHROPIC_API_KEY` só no ambiente | Dois testes `llm` verdes e cópia dos termos guardada |
| 0.3 | Object storage | Você | Ler `docs/decisoes/object-storage.md` e assinar a tabela final (manter `pgsty/minio` por digest é a recomendação) | Linha de assinatura preenchida |
| 0.4 | Objetos órfãos | Você | Apagar os 344 objetos sintéticos em claro do bucket de desenvolvimento (`docker compose exec minio mc rm --recursive --force local/lupa-autos/<prefixos>` com a lista que `scripts/recifrar_objetos_legado.py` imprime), ou recriar o bucket do zero antes do piloto | `scripts/recifrar_objetos_legado.py` reporta 0 em claro |
| 0.5 | Dados jurídicos | Gabinete confirma; agente aplica | Entregar ao gabinete a lista de `docs/validacoes.md` ("a confirmar"): calendários de feriados e recesso do TJGO, prazos dos recursos, tabela do art. 109, `tipos_penais.yaml`, regras de borda (intervalo igual ao prazo, 70 anos, 90 dias exatos, duas intimações quando a defesa recorre, intimação na sexta). Cada confirmação vira edição de YAML com `versao` nova | YAMLs atualizados e suíte verde |
| 0.6 | Advogado | Você contrata; advogado revisa | Entregar as seis minutas de `docs/conformidade/` com a lista de itens abertos da revisão 8.2, §5 | Minutas aprovadas e versão 1.0 |
| 0.7 | Geolocalização por IP | Você (opcional) | Conta gratuita na MaxMind, baixar GeoLite2-City, apontar `LUPA_GEOIP_CAMINHO` | `/auditoria` mostra cidade em vez de "desconhecida" |

Ordem sugerida: 0.2 e 0.3 no primeiro dia (destravam o resto); 0.1 e 0.5 em paralelo (uma semana); 0.6 corre ao lado e pode terminar na Fase 1; 0.4 e 0.7 quando quiser.

---

## Fase 1 — Servidor do piloto (8.1 no mundo real, 2 a 3 dias)

Pré-requisitos: máquina própria com Docker, disco separado para dados, domínio apontando para ela (ou certificado fornecido), duas pessoas de confiança além de você para as partes do Vault.

1. **Instalar.** `docs/operacao.md` seção 2 ou `scripts/instalar_piloto.sh` (produção). Use `docker-compose.prod.yml`. Preencha o `.env` sem reaproveitar nada do desenvolvimento.
2. **Vault com três partes.** `LUPA_AMBIENTE=producao` no `vault_inicializar.sh`: cada parte aparece uma vez; entregue uma a cada pessoa, fora de qualquer arquivo. Guarde o procedimento de unseal (seção 4) impresso.
3. **Certificado.** `LUPA_TLS_MODO=acme` com domínio e e-mail, ou `fornecido` com os arquivos. Confirme HSTS no navegador.
4. **Backup.** Confirme o `backup-agendado` no perfil de produção, defina `LUPA_BACKUP_DIR` e `LUPA_BACKUP_CHAVES_DIR` em discos diferentes, e faça uma restauração de teste no próprio servidor (seção 6).
5. **Monitoramento.** Perfil `monitoramento` ligado; defina um canal para os alertas (e-mail ou mensageria), que hoje não existe.
6. **Conferir.** `python scripts/conferir_piloto.py` no host: a meta é 15 atendidos e 2 manuais resolvidos. Guarde a saída em `docs/etapas/`.
7. **Contas.** `criar_admin.py`, depois crie o gabinete e o desembargador pela interface; o desembargador cria os assessores.

---

## Fase 2 — 8.3 Cadastro e treinamento (1 dia)

- Cada usuário: primeiro acesso, autenticador, troca de senha, aceite dos termos (versão 1.0 do advogado).
- Sessão de treinamento com o `guia-assessor.md` e o `guia-desembargador.md` abertos, num processo sintético gerado por `scripts/gerar_autos.py` e ingerido no piloto.
- Critério: cada assessor faz login, abre o processo sintético, encontra uma evidência pelo visualizador, refaz à mão a conta de uma validação e faz uma pergunta ao chat, sem ajuda.
- Peça a um assessor que leia o guia inteiro e anote o que não entendeu (pendência 7.9).

---

## Fase 3 — 8.4 Primeiro processo real (1 a 2 dias)

- Confirmar que o processo é público e não tem peça sigilosa.
- Seguir `docs/calibracao-projudi.md`: `scripts/calibrar.py` sobre o arquivo exportado gera o relatório de diagnóstico, páginas, peças, eventos e achados.
- Um assessor confere item a item e preenche a tabela de medidas da seção 4 do roteiro de calibração (diagnóstico, fronteiras, tipo, origem, data, eventos, achados).
- **Agente:** com o relatório conferido, ajustar regras de fronteira, títulos, padrões de evento e calendários conforme a seção 5 do roteiro (subir `versao` dos YAML), e rodar a suíte. Eu reviso.
- Critério: precisão de datas ≥ 99% no processo real, nenhuma data inventada, diagnóstico correto.

---

## Fase 4 — 8.5 e 8.6 Gabarito e ajustes (2 semanas)

- Escolher 5 a 10 processos públicos variados (apelação, HC, agravo em execução; nativo e digitalizado; tamanhos diferentes).
- Para cada um: ingerir, gerar o relatório de calibração, e um assessor anota o gabarito (peças, datas, resultado esperado das três validações). Guardar em repositório separado, sem subir ao git do produto.
- **Agente:** rodar `scripts/medir.py` contra cada gabarito, corrigir regras e YAMLs, repetir até datas ≥ 99% e fronteiras ≥ 95% nos reais. Eu reviso cada rodada.
- Critério: métricas registradas em `docs/etapas/RELATORIO-ETAPA-8.6.md`, calendários oficiais do TJGO carregados.

---

## Fase 5 — 8.7 Uso acompanhado (2 a 4 semanas)

- Os assessores usam o Lupa nos processos reais do fluxo normal, só públicos.
- Para cada processo, preencher uma linha: achados confirmados, achados rejeitados e por quê, perguntas ao chat úteis e recusadas, tempo gasto com e sem a ferramenta (estimativa), incidentes.
- Semanalmente: exportar `/auditoria/relatorio-uso`, conferir custo estimado, conferir `conferir_piloto.py` e a integridade da cadeia de auditoria.
- Qualquer resposta bloqueada ou processo em revisão: seguir `docs/conformidade/plano-de-incidentes.md` e registrar.

---

## Fase 6 — 8.8 Revisão de segurança (paralela à Fase 5)

- Contratar teste de intrusão externo ou revisão independente com escopo explícito: autenticação e MFA, isolamento por gabinete (RLS e rotas), injeção via autos (corpus `.sinteticos/injecao/` disponível), exfiltração pelo agente, exposição do proxy, Vault e backups.
- Entregar ao revisor `docs/criptografia.md`, `docs/agente.md`, `docs/auditoria.md`, `docs/operacao.md` e o `docker-compose.prod.yml`.
- **Agente:** corrigir os achados críticos e altos; eu reviso. Critério: relatório recebido e críticos corrigidos antes de ampliar o uso.

---

## Fase 7 — 8.9 e 8.10 Relatório e decisão (1 semana)

- **Agente:** consolidar `docs/relatorio-piloto.md` a partir das planilhas da Fase 5, das métricas da Fase 4, do relatório de uso, do custo por processo e do feedback dos assessores. Eu reviso.
- Apresentar ao desembargador.
- Decidir a continuidade e priorizar o backlog da versão 2, que já tem candidatos registrados nas revisões: catálogo cível, prescrição pela pena aplicada e pena aplicada como fato, validações semânticas, anonimização para processos sigilosos, múltiplos réus e concurso de crimes, destaque por caractere no visualizador, retomada de upload, desfazer correção, filtros de auditoria por nome, auto-unseal com KMS, canal de alertas, mais gabinetes.

---

## Resumo em uma linha por semana

| Semana | Foco |
| --- | --- |
| 1 | Fase 0: chave da API e termos, storage, pseudonimização (agente), dados jurídicos ao gabinete, advogado contratado |
| 2 | Fase 0 termina; Fase 1: servidor, Vault com três pessoas, certificado, backup, conferência |
| 3 | Fase 2 e 3: contas, treinamento, primeiro processo real e calibração |
| 4 e 5 | Fase 4: gabarito com 5 a 10 processos e ajustes |
| 6 a 9 | Fase 5 e 6: uso acompanhado e revisão de segurança |
| 10 | Fase 7: relatório e decisão |
