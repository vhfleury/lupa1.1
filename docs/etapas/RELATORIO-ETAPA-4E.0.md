# Relatório da Etapa 4E.0 — Tarefas prévias (texto branco, ZIP lento, duas colunas)

## O que foi feito

1. **Defeito de `sinais.py` (REVISAO-ETAPA-4D, seção 3).** `_invisivel` passou a comparar
   `int(span["color"]) & 0xFFFFFF == 0xFFFFFF`: o PyMuPDF 1.25 devolve a cor com o byte de alfa
   (branco chega como `-1`). Teste novo
   `tests/ingestao/test_fronteiras.py::test_texto_branco_conta_como_invisivel_com_alfa_do_pymupdf`
   (página com texto branco: `caracteres_invisiveis` = 18). `VERSAO_EXTRATOR` subiu de `4d.1`
   para `4e.0`, porque uma página nativa com texto branco agora vai à abstenção (OCR e
   comparação de camadas) e o resultado gravado muda.
2. **Diagnóstico de ZIP lento.** A causa não era abrir o PDF inteiro: medido no contêiner, a
   inspeção de uma entrada pequena leva 0,002 a 0,03 s, e a partida de um filho do sandbox
   (interpretador + PyMuPDF + limites) leva 0,86 a 0,89 s. Correção: `parser_pdf.main` aceita
   vários caminhos e devolve `{"ok": true, "itens": [...]}`; `sandbox.inspecionar_pdfs` inspeciona
   um grupo num único filho e, se o filho do grupo falhar (memória, CPU, tempo), reinspeciona
   cada entrada sozinha para o motivo ficar com a culpada. O worker inspeciona as entradas em
   grupos de 32 (`ENTRADAS_POR_FILHO`), gravando o lote de cada entrada como antes (lease
   renovado por entrada, retomada idempotente). O `scripts/medir_extracao.py diagnostico` usa o
   mesmo caminho. A inspeção continua decodificando todo o conteúdo (é isso que expõe stream
   gigante ao limite de memória), então ler só as primeiras páginas não foi adotado.
3. **Duas colunas no gerador sintético (REVISAO-ETAPA-4B, seção 5, item 3).**
   `Configuracao.duas_colunas` (e `--duas-colunas` na CLI) diagrama o corpo das peças desses
   tipos em duas colunas (largura de coluna (465 − 18)/2 pt). A folha recebe o elemento novo
   `Elemento.DUAS_COLUNAS` e o `texto` do gabarito é a ordem de leitura (coluna esquerda inteira,
   depois a direita). Os dez processos de referência não foram regerados (padrão vazio).
   Testes em `tests/sinteticos/test_duas_colunas.py` geram um processo de 30 folhas em memória
   (laudo e termo de depoimento em duas colunas) e conferem: só essas peças têm o elemento, há
   linhas na coluna direita, e `extrair_texto_nativo` devolve exatamente a ordem de leitura do
   gabarito nas 16 folhas em duas colunas (fora a marca d'água, que não é texto visível).

## Matriz do roteador depois da correção (dez processos, `pdf_liso`, 15.647 folhas)

| Gabarito \ Roteador | nativa | ocr | vazia | abstenção |
|---|---|---|---|---|
| nativa | **10.708** | 0 | 0 | 0 |
| capa | **10** | 0 | 0 | 0 |
| digitalizada | 0 | **3.426** | 0 | 0 |
| hibrida_corpo | 0 | 0 | 0 | **1.190** |
| hibrida_assinatura | 0 | 0 | 0 | **83** |
| vazia | 0 | 0 | **230** | 0 |

Corretos 15.647/15.647; falso negativo perigoso 0/4.699; texto nativo igual ao gabarito em
10.718/10.718. Idêntica à da 4C.4: os processos de referência não têm texto branco (ele está
só no corpus de injeção da 4B.8), então nenhum limiar mudou e `roteador.yaml` continua na
versão `1`.

## Tempo do diagnóstico de ZIP (`semente_01/zip_por_peca`, 51 entradas)

| | Total | Por entrada |
|---|---|---|
| Antes (um filho por entrada) | 46,38 s | 0,91 s |
| Depois (grupos de 32 num filho) | 2,15 s | 0,042 s |

Os resultados das 51 inspeções e as fronteiras do manifesto são idênticos nos dois caminhos.
Para o ZIP de 878 entradas citado na revisão, a estimativa cai de ~12 min para ~40 s.

## Decisões não previstas

- Versão do extrator subida (`4e.0`) em vez de manter `4d.1`: a correção muda a rota de
  páginas com texto branco.
- Grupo de 32 entradas por filho: com o limite de 2 GB e 300 s por filho, cabe com folga nas
  peças típicas; o pior caso (grupo com uma bomba) custa 32 reinspeções individuais.

## Comandos e saída resumida

```
docker compose run --rm api python scripts/medir_extracao.py roteador
  -> corretos 15647/15647, falso_negativo_perigoso 0, texto_nativo igual 10718
docker compose run --rm api python <script de tempo> (inventário + inspeção, semente_01)
  -> 51 antes 46.38 depois 2.15 iguais True True
pytest tests/ingestao/test_sandbox.py tests/sinteticos/test_duas_colunas.py -> 25 passed
```

## Checklist

| Item | Evidência |
|---|---|
| Máscara de cor em `sinais.py` | teste do texto branco: 18 invisíveis |
| Matriz do roteador reexecutada | 15.647/15.647, igual à 4C.4; `roteador.yaml` versão 1 mantida |
| ZIP: tempo antes e depois | 46,38 s → 2,15 s (0,91 → 0,042 s por entrada) |
| Falha no grupo isolada por entrada | `test_grupo_com_bomba_reinspeciona_cada_entrada` |
| Duas colunas com gabarito de leitura | 16/16 folhas com a ordem do gabarito |
