# Revisão — Subetapa 8.2 (conformidade do piloto)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Seis minutas em `docs/conformidade/` e o relatório `RELATORIO-ETAPA-8.2.md`. Todas com o cabeçalho "MINUTA para revisão de advogado; não é parecer jurídico", versão 0.1, data, fim de linha LF. Nenhum arquivo da 8.1 tocado.

Citações normativas conferidas por amostragem contra as fontes que o executor registrou: Resolução CNJ 615/2025 (cópia do STJ) art. 19, §§ 2º, 3º I a V, 6º, 7º e 8º, Anexo AR1 a AR5 e BR1 a BR8, coerentes com o que esta revisão já havia lido na Etapa 3 de planejamento; LGPD arts. 5º, 7º, 11, 18, 37, 39, 41, 46 e 48 no texto do Planalto; Resolução CD/ANPD 15/2024 arts. 6º, 9º e 10 (três dias úteis para comunicar ANPD e titulares; registro de incidentes por cinco anos), com link e data de consulta. Nenhum artigo citado de memória; onde não houve confirmação, o texto diz "a confirmar pelo advogado".

## 2. Critérios de saída

| Documento | Resultado | Observação |
| --- | --- | --- |
| Termos de uso | ok | tabela pode/não pode do contrato do agente; vedação de sigiloso; MFA; auditoria com IP; aceite |
| Aviso de tratamento | ok | duas partes: usuários e pessoas citadas nos autos; diz o que vai e o que não vai ao fornecedor do modelo |
| Registro de operações | ok | sete fluxos em tabela |
| Relatório de uso ao tribunal | ok | modelo para o art. 19, § 7º com exemplo sintético |
| Plano de incidentes | ok | quatro níveis, papéis, prazos da Res. ANPD 15/2024, registro, ensaios da 7.10 em anexo |
| Checklist do piloto | ok | 16 itens antes do primeiro processo real |

## 3. Achado relevante levantado pela 8.2 e confirmado no código

A pseudonimização implementada na Etapa 4F e usada pelo agente na Etapa 5 cobre **só nome e CPF dos réus** (`reu_identidade`). Nomes de vítimas e testemunhas, que aparecem em depoimentos, certidões e sentenças, vão ao modelo externo dentro dos trechos. Os requisitos da primeira versão (seção 6) dizem que nomes e identificadores pessoais são pseudonimizados nos prompts, sem restringir a réus, e os princípios de desenho tratam vítimas e menores no nível mais restritivo. É uma lacuna real entre requisito e implementação, não um defeito dos documentos.

Consequência: o aviso de tratamento e o registro de operações, como escritos, afirmam que nome e CPF do réu não vão ao fornecedor do modelo, o que é verdade, mas não podem afirmar o mesmo das demais pessoas. O executor deixou isso marcado como verificação técnica, corretamente.

Decisão para o responsável técnico, antes do primeiro processo real:
- **Opção A (recomendada):** estender a pseudonimização a vítimas e testemunhas identificadas na denúncia, nos termos de depoimento e nas certidões, com a mesma estrutura de `reu_identidade` (uma tabela de identidades por papel), e medir recall em processos sintéticos que já geram esses nomes. É trabalho de código (Etapa 4F estendida), com teste de que nenhum nome cadastrado chega ao modelo.
- **Opção B:** aceitar a limitação no piloto, só com processos públicos, registrando no aviso de tratamento que nomes de outras pessoas citadas podem constar dos trechos enviados ao fornecedor do modelo, sob contrato que veda treinamento. Menos trabalho, mais exposição.

## 4. Decisão

**Aprovado como minuta**, condicionado à revisão de advogado antes do aceite pelos usuários e à decisão sobre a pseudonimização de vítimas e testemunhas (seção 3).

## 5. Itens para o advogado (registrados pelo executor)

Base legal para dados dos autos tratados por particular e dados de natureza penal; hipótese da transferência internacional ao fornecedor do modelo; encarregado e canal de atendimento; retenção da auditoria; forma do aceite, responsabilidade por indisponibilidade e remuneração; aplicação do registro do § 6º e da capacitação do § 3º, I ao uso privado; existência de regulamento do TJGO para o § 7º; critério de risco relevante e meio de comunicar titulares que não usam o sistema.

## 6. Pendências técnicas confirmadas

- Termos atuais da API da Anthropic (treinamento, retenção, local de processamento) não foram consultados; é o item 6 do checklist e precisa de leitura dos termos vigentes pelo responsável técnico antes do piloto.
- Pseudonimização de vítimas e testemunhas (seção 3).
