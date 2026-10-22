# Auditoria do Lupa

Este texto explica, sem jargão, o que o Lupa anota sobre o uso do sistema, o que ele nunca anota
e como conferir que ninguém mexeu nessas anotações.

## Para que serve

Cada vez que alguém entra no sistema, abre um processo, faz uma pergunta ao assistente ou muda a
conta de outra pessoa, o Lupa grava uma linha na **trilha de auditoria**. A trilha responde a
perguntas como "quem abriu este processo e quando?" e serve de base para o relatório que o
magistrado entrega ao tribunal sobre o uso de inteligência artificial (art. 19, §7º).

## O que é registrado

Cada evento guarda apenas:

| Campo | Exemplo | Para quê |
| --- | --- | --- |
| Quando | 20/10/2026 14:03:12 | Ordem dos fatos |
| Quem | identificador do usuário | Saber quem agiu |
| Gabinete | identificador do gabinete | Separar a trilha de cada gabinete |
| Processo | identificador do processo | Saber sobre qual processo |
| Ação | `processo_aberto`, `login_falha`... | O que foi feito |
| Objeto | tipo e identificador (página 12, fato X, usuário Y) | Sobre o que foi feito |
| Resultado | `ok`, `falha`, `negado`, `bloqueado` | Se deu certo |
| IP e localização aproximada | 200.1.2.3 · Goiânia, Goiás, Brasil | De onde veio o acesso |
| Versão do modelo e do prompt | quando há chamada ao assistente | Qual "versão" respondeu |

Ações registradas: entrada e saída do sistema (inclusive tentativas erradas e bloqueios), código
do autenticador certo ou errado, troca e reinício de senha ou do autenticador, criação,
desativação e reativação de usuários, criação de gabinete, criação e envio de processo,
abertura de processo (inclusive a leitura do índice e das peças), página vista, busca,
pergunta ao chat, anotação, correção de fato, reclassificação de peça
(`peca_reclassificada`, uma por peça nova, com o id da peça),
execução de validação, chamada ao modelo, consulta e exportação da própria auditoria.

Quando o **administrador** abre conteúdo de autos de um gabinete, além do evento normal o Lupa
grava um evento separado, `admin_acesso_conteudo`, na trilha daquele gabinete, para que o
desembargador veja em destaque.

Quando alguém tenta abrir um processo de outro gabinete, a tela responde "não encontrado" (sem
revelar que o processo existe) e a tentativa fica registrada como `processo_aberto` com resultado
`negado`.

A localização é aproximada (cidade, estado, país) e vem de uma base offline; acessos de dentro
da rede do tribunal aparecem como "rede interna"; quando não dá para saber, aparece
"desconhecida". Uma falha nessa consulta nunca impede o registro do evento.

## O que nunca é registrado

- Texto dos autos, de páginas, de fatos ou de anotações.
- Texto de perguntas feitas ao chat e das respostas.
- Senhas (nem erradas), códigos do autenticador, tokens de sessão.
- O nome digitado numa tentativa de entrada com usuário que não existe (às vezes a pessoa digita
  a senha no campo errado).

Isso é garantido pelo formato do evento: ele tem só os campos da tabela acima, sem nenhum campo
de texto livre. Um teste automático percorre todos os eventos gravados e confere que nenhum
contém campos proibidos (`senha`, `token`, `texto`, `conteudo`, `pergunta`, `resposta`...) nem
os segredos usados no teste.

## Por que ninguém consegue alterar a trilha

1. **Só acrescenta.** O banco de dados recusa qualquer alteração ou exclusão de evento, mesmo
   vinda do administrador do banco (há uma trava interna que barra `UPDATE`, `DELETE` e
   `TRUNCATE`). O usuário que a aplicação usa nem tem permissão para tentar.
2. **Corrente de lacres.** Cada evento carrega um "lacre" (hash SHA-256) calculado a partir do
   seu próprio conteúdo **e do lacre do evento anterior** do mesmo gabinete. Se alguém mudar
   qualquer letra de um evento antigo, o lacre dele deixa de bater e a corrente se rompe ali.
   Eventos sem gabinete (como tentativas de entrada de usuários inexistentes e ações do
   administrador fora de gabinetes) formam uma corrente própria, a global.
3. **Numeração sem buracos.** Cada evento tem um número de ordem dentro da corrente; o banco não
   aceita dois eventos com o mesmo número, então dois registros simultâneos nunca "pulam" ou
   duplicam um elo.

## Como verificar a integridade

Quem pode ver a auditoria (desembargador para o próprio gabinete, administrador para todos)
chama:

```
GET /auditoria/verificar                 # desembargador: seu gabinete
GET /auditoria/verificar?gabinete_id=... # administrador: um gabinete
GET /auditoria/verificar                 # administrador: corrente global
```

A resposta diz quantos eventos foram conferidos e se a corrente está íntegra. Se não estiver,
aponta **o primeiro evento com problema** e o motivo:

- `hash`: o conteúdo do evento foi alterado depois de gravado;
- `encadeamento`: o evento não aponta para o lacre do anterior (evento removido ou inserido);
- `sequencia`: falta ou sobra número na ordem.

## Consultar, exportar e relatar

- `GET /auditoria` com filtros por gabinete, usuário, processo, ação, período e IP; resultado em
  páginas, do mais recente para o mais antigo.
- `GET /auditoria/exportar?formato=csv` (ou `json`): baixa os eventos filtrados. O próprio ato de
  exportar vira um evento.
- `GET /auditoria/relatorio-uso?processo=...` ou `?usuario=...`: contagem por ação, primeiro e
  último acesso, e quais versões do modelo e do prompt foram usadas. É o material para informar
  o tribunal.

Toda consulta à auditoria também fica registrada (`auditoria_consultada`).

## Custo estimado no relatório de uso (6.9)

`GET /auditoria/relatorio-uso` devolve `custo_estimado`: tokens de `chamada_modelo` por modelo
(por processo: todas as chamadas; por usuário: as das conversas dele) vezes a tabela versionada
`src/lupa/agente/dados/precos.yaml` (`versao`, `fonte`, preço por milhão de tokens de entrada e
saída; `claude-opus-5-5`: US$ 4 / US$ 20). É estimativa, a confirmar na fatura; modelo fora da
tabela aparece com custo nulo. Ações novas: `processo_em_revisao` e `revisao_liberada`.
