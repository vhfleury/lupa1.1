# Relatório da subetapa 8.2 — Conformidade do piloto

21 de outubro de 2026 · executor

## 1. Entregue (todos como MINUTA para revisão de advogado, versão 0.1)

| Arquivo | Conteúdo |
| --- | --- |
| `docs/conformidade/termos-de-uso.md` | finalidade, pode/não pode, responsabilidade do magistrado, conferência humana, vedação de sigilo, conta pessoal e MFA, auditoria com IP e localização, limites, suporte, encerramento, aceite |
| `docs/conformidade/aviso-de-tratamento.md` | parte A (usuários) e parte B (titulares nos autos), com o que vai e o que não vai ao modelo |
| `docs/conformidade/registro-de-operacoes.md` | 7 fluxos em tabela |
| `docs/conformidade/relatorio-uso-tribunal.md` | modelo para o art. 19, § 7º, e exemplo sintético |
| `docs/conformidade/plano-de-incidentes.md` | fundamentos, papéis, classificação, prazos, modelo de registro, ensaios 7.10 como anexos |
| `docs/conformidade/checklist-piloto.md` | 16 itens antes do primeiro processo real |

`docs/guia-desembargador.md` não foi alterado (já remete ao relatório de uso). Arquivos da 8.1 não tocados.

## 2. Fundamentos e fontes (consultados em 21/10/2026)

- **Res. CNJ 615/2025**, cópia do STJ: https://www.stj.jus.br/internet_docs/biblioteca/clippinglegislacao/Res_615_2025_CNJ.pdf — conferido o texto literal do art. 19, §§ 2º, 3º (I a V), 6º, 7º, 8º e do Anexo (AR1 a AR5, BR1 a BR8).
- **LGPD (Lei 13.709/2018)**, Planalto: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm — conferidos arts. 5º, 7º (II, V, VI, IX), 11 (II, "d"), 18, 37, 39, 41, 46 e 48.
- **Resolução CD/ANPD nº 15/2024**, DOU: https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024 — arts. 6º e 9º (três dias úteis para ANPD e titular) e 10 (registro por cinco anos).
- Internos: `requisitos-v1.md` (seções 2, 3, 6, 7, 10, 11), `docs/agente.md`, `docs/operacao.md` (10, 11, 13), `docs/backup.md` (retenção 30 dias), `docs/auditoria.md`, `CONFORMIDADE-GERAL.md`. O `arquitetura.md` (tribunal controlador) foi usado só como referência; prevalece o contexto fixo (fornecedor controlador).

## 3. Para o advogado decidir

1. Base legal para dados dos autos tratados por particular em apoio a magistrado (art. 7º, VI / 11, II, "d" vs. legítimo interesse) e tratamento de dados de natureza penal.
2. Hipótese legal da transferência internacional ao fornecedor do modelo.
3. Encarregado: indicação ou dispensa; canal e forma de publicidade do aviso aos titulares.
4. Prazo de retenção da auditoria.
5. Forma do aceite dos termos; responsabilidade por indisponibilidade; remuneração do piloto.
6. Aplicação a uso privado do registro previsto no art. 19, § 6º, e da capacitação do § 3º, I.
7. Existência de regulamento do TJGO para o § 7º e se o modelo de relatório o atende.
8. Critério de "risco ou dano relevante" e meio de comunicar titulares que não interagem com o sistema; conferir se a Res. CD/ANPD 15/2024 sofreu alteração.

## 4. Não confirmado

- Termos atuais da API da Anthropic (treino, retenção, local de processamento): não consultados; ficam no checklist (item 6).
- Se a pseudonimização cobre nomes de vítimas e testemunhas além do réu: registrado como verificação técnica no aviso.
- Os PDFs de pesquisa da raiz não foram necessários para os fundamentos citados.
