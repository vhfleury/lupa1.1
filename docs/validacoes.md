# Validações automáticas (guia do assessor)

O Lupa confere três pontos dos processos criminais fazendo contas com datas que vieram dos autos.
Cada conferência gera um **achado** com um de três resultados:

- **conforme**: a conta não encontrou problema;
- **atenção**: a conta encontrou um possível problema (recurso fora do prazo, prescrição, prisão
  sem revisão);
- **verificar**: o sistema não conseguiu concluir, porque falta uma data, há duas datas
  diferentes para a mesma coisa ou ocorreu um erro. O achado diz o que falta.

Todo achado traz, para cada data usada, o fato de onde ela saiu e o trecho dos autos (evidência)
que a sustenta. Assim você refaz a conta sem confiar no sistema. A explicação em texto é montada
por um modelo de frase fixo, nunca por inteligência artificial.

Os números jurídicos (prazos, tabela do art. 109, feriados, recessos) ficam em arquivos de dados
versionados em `src/lupa/validacoes/dados/`, cada um com `versao` e `fonte`. Mudar um prazo é
editar esse arquivo, não o programa.

## 1. Tempestividade do recurso

**Fatos usados:** tipo do recurso e quem recorre (defesa ou MP); data da intimação do defensor
e data da intimação do réu (quando a defesa recorre) ou data da intimação do MP (quando o MP
recorre); data da interposição.

**Regra:**

1. Prazos: apelação 5 dias (art. 593 CPP); recurso em sentido estrito 5 dias (art. 586 CPP);
   embargos de declaração 2 dias (art. 619 CPP).
2. Quando a defesa recorre, o prazo conta da **última** intimação entre réu e defensor
   (art. 392 CPP).
3. Contagem em dias corridos: não se conta o dia da intimação e conta-se o último dia
   (art. 798, § 1º, CPP).
4. Dias de suspensão de prazo (recesso) não são contados.
5. Se o último dia cai em sábado, domingo, feriado ou suspensão, o prazo vai para o próximo dia
   com expediente (art. 798, § 3º, CPP).
6. Interposição até o vencimento: **conforme**. Depois: **atenção**, com quantos dias depois.

**Base legal:** arts. 392, 586, 593, 619 e 798 do CPP.

**O que conferir à mão:**

- se as certidões de intimação são válidas (pessoal, edital, réu preso);
- se o recurso é mesmo o informado (o sistema não verifica cabimento);
- os feriados e suspensões listados no achado contra o calendário oficial do TJGO;
- se havia motivo para o prazo começar em outro dia (ex.: intimação numa sexta-feira,
  Súmula 310 do STF, que o sistema **não** aplica);
- prazos especiais (Juizado, Lei de Drogas, ECA, assistente de acusação), que o sistema não
  conhece.

## 2. Prescrição pela pena em abstrato

**Fatos usados:** pena máxima do crime (em meses), data do fato, data do recebimento da denúncia,
data da publicação da sentença condenatória (se houver), data de nascimento do réu (opcional).

**Regra:**

1. A pena máxima define o prazo pela tabela do art. 109 do CP: acima de 12 anos, 20 anos; acima
   de 8 até 12, 16 anos; acima de 4 até 8, 12 anos; acima de 2 até 4, 8 anos; de 1 até 2,
   4 anos; abaixo de 1 ano, 3 anos.
2. O prazo cai pela metade se o réu tinha menos de 21 anos na data do fato ou 70 anos ou mais
   na data da sentença (art. 115 do CP).
3. Marcos considerados: fato, recebimento da denúncia e publicação da sentença condenatória
   recorrível (art. 117, I e IV, do CP). O sistema calcula cada intervalo (fato → recebimento;
   recebimento → sentença; último marco → data de referência) e compara com o prazo.
4. Um intervalo é **atenção** quando a data final passa da data inicial somada do prazo.

**Base legal:** arts. 109, 115 e 117, I e IV, do CP.

**Limitações (o sistema não considera):** pronúncia e sua confirmação, acórdão condenatório,
causas suspensivas (art. 116 do CP, art. 366 do CPP, suspensão condicional do processo),
prescrição retroativa, intercorrente e executória, crimes imprescritíveis, concurso de crimes e
aumentos ou diminuições que mudam a pena máxima.

**O que conferir à mão:** a pena máxima (com causas de aumento e diminuição), cada marco nos
autos, causas suspensivas, a idade do réu e as limitações acima.

## 3. Revisão da prisão preventiva a cada 90 dias

**Fatos usados:** data da decretação da preventiva e datas das decisões que revisaram a
necessidade da prisão (pode não haver nenhuma).

**Regra:** as datas são postas em ordem; calcula-se cada intervalo entre decretação e revisões
e da última decisão até a data de referência. Intervalo acima de 90 dias é **atenção**, e o
achado aponta qual.

**Base legal:** art. 316, parágrafo único, do CPP.

**O que conferir à mão:** se cada decisão listada como revisão de fato reexaminou a necessidade
da prisão com fundamentação; se o réu continua preso; se houve soltura e nova prisão no meio da
cadeia (o sistema não sabe disso).

## Pontos que dependem de confirmação do gabinete

1. **Intervalo exatamente igual ao prazo de prescrição:** o sistema considera **não prescrito**
   (ex.: prazo de 3 anos, fato em 10/01/2030 e recebimento em 10/01/2033). Pelo art. 10 do CP
   (o dia do começo é incluído), pode-se entender que a prescrição se consuma na véspera do
   aniversário. Confirmar qual regra adotar.
2. **Maior de 70 anos (art. 115):** o sistema aplica a redução a quem já completou 70 anos na
   data da sentença. Confirmar.
3. **Intervalo de exatamente 90 dias na preventiva:** o sistema considera **conforme**; só acima
   de 90 dias é atenção. Confirmar.
4. **Recesso forense (art. 798-A do CPP) e prazos de réu preso:** o arquivo
   `suspensoes_prazo.yaml` aplica o recesso de 20/12 a 20/01 a todos os recursos. Confirmar as
   exceções (réu preso, medidas urgentes) e incluir as portarias de suspensão do TJGO.
5. **Feriados do TJGO:** `feriados/tjgo.yaml` é **provisório** (datas marcadas "a confirmar").
   Substituir pelo calendário oficial do tribunal. `feriados/nacionais.yaml` inclui Carnaval,
   Semana Santa e Corpus Christi como dias sem expediente forense; confirmar.
6. **Prazos e artigos citados** (arts. 586, 593, 619, 798 do CPP; 109, 115, 117 do CP; 316 do CPP)
   foram registrados de memória a partir do catálogo e precisam ser conferidos com o texto legal
   vigente.

## Como conferir um processo pela linha de comando

```bash
docker compose exec api python -m lupa.validacoes --fatos /dev/stdin --materia criminal \
  --referencia 2026-10-20 < docs/exemplos/fatos.json
```

`docs/exemplos/fatos.json` é um processo sintético que serve de modelo do formato de entrada.
A saída é a lista de achados em JSON.

### Formato dos fatos

O formato é o esquema `Fato` do domínio (`lupa.dominio.esquemas`), o mesmo gravado no banco.
Cada fato tem `id` e `processo_id` (UUID), `tipo` (um dos valores de `TipoFato`), `valor`,
`evidencias` (ao menos uma), `extraido_por`, `versao_extrator`, `confianca` e, opcionalmente,
`status` (padrão `automatico`). Cada evidência tem `id` e `pagina_id` (UUID), `trecho`, `inicio` e
`fim` (`fim` maior que `inicio`); `hash_trecho` pode ser omitido porque é calculado. Datas vão em `valor` como `"AAAA-MM-DD"`. O tipo de
recurso vai como `{"tipo": "apelacao" | "rese" | "embargos_declaracao", "recorrente": "defesa" |
"mp"}`. A pena máxima vai em meses (número inteiro). Fatos de um réu específico podem vir como
`{"valor": ..., "reu_id": "..."}`. Em código Python a data também pode ser um `datetime.date`.

A saída da linha de comando é o resultado do motor (sem `id` nem `processo_id`); para gravar,
`lupa.validacoes.adaptador.para_dominio` converte cada resultado no `Achado` do domínio.
