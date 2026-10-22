# Modelo de relatório de uso de ferramenta privada de IA ao tribunal

> **MINUTA para revisão de advogado; não é parecer jurídico.** Versão 0.1 · 21 de outubro de 2026 · subetapa 8.2.

Finalidade: permitir ao magistrado prestar ao tribunal as informações sobre o uso de solução de mercado de IA (Res. CNJ 615/2025, art. 19, § 7º, "na forma do regulamento"). O regulamento do tribunal pode exigir outro formulário; nesse caso, use este modelo como fonte dos dados (a confirmar pelo advogado se o TJGO já editou regulamento).

Fonte dos números: Auditoria → Relatório de uso no sistema, ou `GET /api/auditoria/relatorio-uso?usuario=<id>` / `?processo=<id>`; eventos em `GET /api/auditoria/exportar?formato=csv`. Ver `docs/operacao.md`, seção 11. Nada disso contém conteúdo dos autos.

---

## Modelo

**Ao** [órgão indicado no regulamento do tribunal]
**Magistrado:** [nome] · **Gabinete:** [identificação] · **Período:** [dd/mm/aaaa a dd/mm/aaaa]

1. **Ferramenta e fornecedor.** Lupa, versão [x], ferramenta privada de apoio à conferência de processos, fornecida por Victor Hugo Fleury Barreto, contratada na forma do art. 19, § 2º (o tribunal não oferece solução corporativa equivalente: [confirmar]).
2. **Finalidades** (Anexo, baixo risco): BR1 (extração, organização e resumo de documentos com supervisão humana); BR4 (textos de apoio, sob supervisão e versão final do magistrado; o Lupa não redige atos); BR5 (tarefa preparatória: linha do tempo e validações objetivas); BR8 (pseudonimização na exibição e no envio ao modelo).
3. **Vedações observadas.** Sem valoração de prova (AR2), tipificação (AR3), juízo conclusivo sobre norma ou precedente (AR4), perfilamento (AR1) ou biometria (AR5); o sistema recusa essas perguntas. Uso auxiliar, com conferência humana e responsabilidade integral do magistrado (art. 19, § 3º, II).
4. **Modelo de linguagem.** [modelo e versões, do relatório de uso], Anthropic, por API. Termos do fornecedor conferidos em [data]: vedação de treinamento [sim/não, cláusula], retenção [prazo].
5. **Segurança.** Somente processos públicos; cifra em repouso com chave por processo; pseudonimização antes do envio ao modelo; MFA; auditoria append-only com IP e localização aproximada.
6. **Auditoria disponível.** Registro de cada acesso e ação, exportável em CSV/JSON, à disposição do tribunal mediante solicitação.
7. **Volume de uso no período.**

| Indicador | Valor |
| --- | --- |
| Processos inseridos | |
| Usuários ativos | |
| Perguntas ao chat | |
| Chamadas ao modelo | |
| Tokens (entrada / saída) | |
| Custo estimado (tabela de preços versão [x]) | |
| Respostas bloqueadas pela conferência / processos postos em revisão | |

8. **Declaração.** Declaro que nenhum processo ou peça sigilosa ou em segredo de justiça foi inserido no sistema no período, e que todo resultado usado foi conferido nos autos.

[Local, data] · [assinatura]

Anexos: relatório de uso exportado; CSV de eventos (opcional).

---

## Exemplo preenchido (dados sintéticos, nenhum dado real)

**Magistrado:** Desembargador Exemplo Sintético · **Gabinete:** GAB-TESTE-01 · **Período:** 01/11/2026 a 30/11/2026

1. Lupa, versão 1.0.0-piloto, fornecido por Victor Hugo Fleury Barreto, art. 19, § 2º.
2. BR1, BR4, BR5, BR8, conforme o modelo.
3. Vedações conforme o modelo; 4 perguntas recusadas no período por pedirem valoração.
4. Modelo `claude-exemplo-1` (Anthropic). Termos conferidos em 28/10/2026: [cláusula de não treinamento]; retenção [prazo].
5. e 6. Conforme o modelo.
7. Volume:

| Indicador | Valor |
| --- | --- |
| Processos inseridos | 6 |
| Usuários ativos | 3 (1 desembargador, 2 assessores) |
| Perguntas ao chat | 142 |
| Chamadas ao modelo | 391 |
| Tokens (entrada / saída) | 4.210.000 / 187.000 |
| Custo estimado | R$ 112,40 (tabela de preços v2026-10) |
| Bloqueios / revisões | 1 / 1 (liberada pelo desembargador em 12/11/2026) |

8. Declaração conforme o modelo.

Goiânia, 01/12/2026 · Desembargador Exemplo Sintético
