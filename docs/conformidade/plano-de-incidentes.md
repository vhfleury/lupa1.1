# Plano de resposta a incidentes com dados pessoais

> **MINUTA para revisão de advogado; não é parecer jurídico.** Versão 0.1 · 21 de outubro de 2026 · subetapa 8.2.

Complementa a seção 10 de `docs/operacao.md` (passos técnicos) com papéis, prazos e comunicação.

## 1. Fundamentos confirmados

- **LGPD, art. 48:** o controlador deve comunicar à autoridade nacional e ao titular o incidente de segurança que possa acarretar risco ou dano relevante aos titulares, em prazo razoável definido pela autoridade, com conteúdo mínimo (natureza dos dados, titulares, medidas de segurança, riscos, motivo da demora, medidas de mitigação). O § 3º manda considerar, na gravidade, se os dados estavam ininteligíveis (cifrados) para terceiros.
- **Resolução CD/ANPD nº 15, de 24 de abril de 2024** (Regulamento de Comunicação de Incidente de Segurança), consultada em 21/10/2026 em https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024 :
  - art. 6º: comunicação à ANPD em **três dias úteis**, contados do conhecimento pelo controlador de que o incidente afetou dados pessoais;
  - art. 9º: comunicação ao titular em **três dias úteis**, contados do mesmo marco;
  - art. 10: registro de todo incidente, **inclusive o não comunicado**, por no mínimo **cinco anos**.
  - Os critérios de "risco ou dano relevante" e a forma do envio (formulário da ANPD) estão na mesma resolução: a confirmar pelo advogado se houve alteração posterior.

## 2. Papéis

| Quem | Faz |
| --- | --- |
| Victor (controlador e responsável técnico) | contém, investiga, decide se há dado pessoal afetado e se há risco relevante, comunica ANPD e titulares, mantém o registro |
| Desembargador (usuário responsável) | avisa Victor de imediato; desativa ou reseta contas do gabinete; decide sobre processo em revisão; avalia se deve informar o tribunal (a confirmar pelo advogado) |
| Assessor | avisa o desembargador e Victor no mesmo dia; não apaga nada |
| Anthropic / hospedagem (operadores) | comunicação ao controlador conforme seus termos (conferir) |

## 3. Classificação

| Nível | Exemplo | Dado pessoal? |
| --- | --- | --- |
| 1 · Evento | processo em revisão por injeção, falso alarme liberado | não |
| 2 · Incidente sem exposição | vazamento só de dado cifrado com Vault e `.env` íntegros; disco cheio | provável não; registrar |
| 3 · Incidente com exposição possível | credencial de usuário comprometida com acesso a autos; `.env` ou `secret_id` vazado junto com dados | sim, avaliar risco |
| 4 · Exposição confirmada | conteúdo de autos ou tabela de identidades lido por terceiro | sim; presume-se risco relevante (a confirmar pelo advogado) |

## 4. Prazos internos

| Momento | Ação |
| --- | --- |
| Imediato | conter (`operacao.md` 10.1 a 10.3); preservar evidência; exportar auditoria |
| Mesmo dia | Victor e desembargador avisados; registro aberto (modelo abaixo) |
| Até 1 dia útil | decidir se afetou dados pessoais (marco de contagem) e o nível |
| Até 3 dias úteis do marco | níveis 3-4 com risco relevante: comunicar ANPD e titulares (Res. CD/ANPD 15/2024, arts. 6º e 9º) |
| Até 5 dias úteis | registro completo, causa e correção |

Comunicação aos titulares dos autos: os titulares não têm contato com o sistema; o meio (direto, por intermédio do gabinete ou comunicação pública) é **a confirmar pelo advogado**.

## 5. Modelo de registro (`docs/incidentes/AAAA-MM-DD-<tipo>.md`)

```
Data e hora de conhecimento:
Quem detectou / como:
Descrição das circunstâncias:
Nível (1-4):
Dados afetados (natureza e categoria):
Número de titulares afetados (crianças, adolescentes, idosos):
Os dados estavam cifrados? Chaves comprometidas?
Avaliação de risco e possíveis danos:
Medidas de contenção e correção (com horários):
Cadeia de auditoria verificada? Resultado:
Comunicado à ANPD? Data / protocolo / motivo de não comunicar:
Comunicado aos titulares? Data / meio:
Desembargador informado em:
Lições e prevenção:
Guardar por no mínimo 5 anos.
```

## Anexo A. Ensaio: credencial de assessor comprometida (Etapa 7.10, 21/10/2026, desenvolvimento, dados sintéticos)

Rotação da chave do gabinete (v1→v2, 1 DEK reenvelopada) → reset de senha → reset de MFA. Execução das rotas em 0,23 s; as duas sessões do assessor passaram a 401; senha antiga recusada; dossiê seguiu abrindo. Classificação: nível 3 simulado. Detalhes: `docs/etapas/RELATORIO-ETAPA-7.10.md` e `docs/operacao.md`, seção 13.

## Anexo B. Ensaio: injeção com processo em revisão (Etapa 7.10, 21/10/2026, desenvolvimento, dados sintéticos)

Pergunta que provoca resposta com instrução → bloqueio pela conferência → processo em revisão → nova pergunta recusada → liberação pelo desembargador → chat volta. 0,26 s. Auditoria: `chamada_modelo` bloqueado, `processo_em_revisao`, `revisao_liberada`. Classificação: nível 1. Detalhes: mesmas fontes do Anexo A.
