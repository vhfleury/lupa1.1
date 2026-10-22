# Modelo de dados (Etapa 1)

Fonte da verdade: `src/lupa/dominio/tabelas.py` (SQLAlchemy) e `src/lupa/dominio/esquemas.py`
(pydantic). A migração `src/lupa/migrations/esquema_v0001.py` é escrita à mão e o teste
`test_migracao_coincide_com_tabelas` garante que ela produz o mesmo esquema das tabelas.

## Diagrama

Toda tabela marcada com `gabinete_id` tem Row Level Security. As setas para `processo`, `arquivo`,
`pagina`, `fato`, `evidencia`, `reu` e `achado` são chaves estrangeiras compostas
`(x_id, gabinete_id)`, o que impede um filho de apontar para um pai de outro gabinete.

```mermaid
erDiagram
    gabinete ||--o{ usuario : "tem (nulo = administrador)"
    gabinete ||--o{ processo : tem
    usuario ||--o{ processo : criado_por
    processo ||--o{ arquivo : tem
    usuario ||--o{ arquivo : enviado_por
    arquivo ||--o{ pagina : tem
    arquivo ||--o{ peca : tem
    pagina ||--o{ evidencia : contem
    processo ||--o{ fato : tem
    fato ||--|{ fato_evidencia : "exige >= 1"
    evidencia ||--o{ fato_evidencia : sustenta
    fato |o--o{ fato : substitui_fato_id
    processo ||--o{ reu : tem
    reu ||--o| reu_identidade : "nome real"
    processo ||--o{ achado : tem
    achado ||--o{ anotacao : sobre
    fato ||--o{ anotacao : sobre
    usuario ||--o{ anotacao : escreve
    usuario |o--o{ evento_auditoria : faz
    gabinete |o--o{ evento_auditoria : de

    gabinete {
        uuid id PK
        text nome
        text chave_criptografia_ref
        timestamptz criado_em
    }
    usuario {
        uuid id PK
        uuid gabinete_id FK "nulo so para administrador"
        text nome_usuario UK
        text papel "assessor|desembargador|administrador"
        text senha_hash
        text mfa_segredo
        bool mfa_confirmado
        bool ativo
        bool troca_senha_obrigatoria
        timestamptz criado_em
    }
    processo {
        uuid id PK
        uuid gabinete_id FK
        text numero_cnj "UK com gabinete_id"
        text classe
        text materia "criminal|civel"
        bool sigiloso
        text status
        timestamptz criado_em
        uuid criado_por FK
    }
    arquivo {
        uuid id PK
        uuid gabinete_id
        uuid processo_id FK
        text sha256 "UK com processo_id"
        int tamanho_bytes
        text nome_original
        text mime
        text chave_storage
        uuid enviado_por FK
        timestamptz enviado_em
    }
    pagina {
        uuid id PK
        uuid gabinete_id
        uuid arquivo_id FK
        int numero "UK com arquivo_id"
        text tipo "nativa|ocr|vazia"
        text texto
        text hash_texto
        jsonb flags
        jsonb sinais "4C"
        jsonb coordenadas "4C"
        jsonb extracao "4C"
        text texto_nativo "4C"
        text texto_ocr "4C"
        text versao_extrator "4C"
        text origem_arquivo "4C"
        int pagina_origem "4C"
    }
    peca {
        uuid id PK
        uuid gabinete_id
        uuid arquivo_id FK
        text tipo
        int pagina_inicial
        int pagina_final
        float confianca
        text metodo "regra|llm|manual"
        text origem
        date data "4E"
        text tipo_data "4E: assinatura|protocolo|juntada"
        uuid data_evidencia_id FK "4E"
        uuid substitui_peca_id FK "4E"
        bool vigente "4E"
        jsonb flags "4E"
        jsonb classificacao "4E"
    }
    evidencia {
        uuid id PK
        uuid gabinete_id
        uuid pagina_id FK
        text trecho
        text hash_trecho "sha256(trecho)"
        int inicio
        int fim
        jsonb bbox
    }
    fato {
        uuid id PK
        uuid gabinete_id
        uuid processo_id FK
        text tipo
        jsonb valor
        text extraido_por
        text versao_extrator
        float confianca
        text status "automatico|confirmado|corrigido"
        uuid substitui_fato_id FK
        timestamptz criado_em
    }
    fato_evidencia {
        uuid fato_id PK
        uuid evidencia_id PK
        uuid gabinete_id
    }
    reu {
        uuid id PK
        uuid gabinete_id
        uuid processo_id FK
        text pseudonimo
    }
    reu_identidade {
        uuid reu_id PK
        uuid gabinete_id
        text nome
        text documento
    }
    achado {
        uuid id PK
        uuid gabinete_id
        uuid processo_id FK
        text validacao
        text versao_catalogo
        text resultado "conforme|atencao|verificar"
        uuid_array fatos_usados
        jsonb valores
        text explicacao
        timestamptz criado_em
    }
    anotacao {
        uuid id PK
        uuid gabinete_id
        uuid achado_id FK
        uuid fato_id FK
        uuid usuario_id FK
        text texto
        timestamptz criado_em
    }
    evento_auditoria {
        uuid id PK
        timestamptz ocorrido_em
        uuid usuario_id FK
        uuid gabinete_id FK
        uuid processo_id
        text acao
        text objeto_tipo
        text objeto_id
        text ip
        text localizacao
        text resultado
        text versao_modelo
        text versao_prompt
        text hash_anterior
        text hash_evento
    }
```

## Regras impostas pelo banco

| Regra | Mecanismo |
| --- | --- |
| Fato sem evidência | `CONSTRAINT TRIGGER fato_exige_evidencia` (adiado para o commit) em `fato`, e `fato_evidencia_nao_orfa` ao apagar a última associação |
| Achado imutável | `BEFORE UPDATE` com `lupa_bloquear_update()` em `achado` |
| Arquivo imutável | o mesmo trigger em `arquivo` |
| Valores de enum | `CHECK <coluna> IN (...)` gerado de `lupa.dominio.enums` (texto + CHECK, para estender sem `ALTER TYPE`) |
| `pagina_final >= pagina_inicial`, `fim > inicio >= 0`, `confianca` em [0, 1], anotação com um único alvo, só administrador sem gabinete | `CHECK` |
| Filho no mesmo gabinete do pai | FKs compostas `(x_id, gabinete_id)` |
| Índices | `(gabinete_id)` em toda tabela com o campo; `(processo_id, tipo)` em `fato`; únicos `(arquivo_id, numero)` em `pagina`, `(processo_id, sha256)` em `arquivo`, `(gabinete_id, numero_cnj)` em `processo` |

Nome real de pessoa só existe em `reu_identidade.nome` e em `usuario` (credenciais).
`gabinete.nome` é nome de órgão, não de pessoa.

## Row Level Security

Toda tabela com `gabinete_id` tem `ENABLE` e `FORCE ROW LEVEL SECURITY` e a política
`<tabela>_por_gabinete`:

```sql
USING      (gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid)
WITH CHECK (gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid)
```

Sem a variável definida nenhuma linha é visível. Superusuários e donos com `BYPASSRLS` ignoram RLS
no PostgreSQL; por isso a migração cria o papel `lupa_app` (`NOLOGIN`, só DML) e a aplicação deve
operar sob ele.

### Como a API define a variável por requisição

1. A dependência de sessão do FastAPI abre uma transação por requisição.
2. Depois de autenticar o usuário (Etapa 3), chama, dentro dessa transação:
   - `lupa.dominio.sessao.assumir_papel_aplicacao(session)` → `SET LOCAL ROLE lupa_app`
     (desnecessário quando a conexão já é feita com um usuário de login membro de `lupa_app`, que é o
     caminho recomendado para produção);
   - `lupa.dominio.sessao.definir_gabinete(session, usuario.gabinete_id)` →
     `set_config('lupa.gabinete_id', '<uuid>', true)`.
3. Ambos valem só até o fim da transação (`SET LOCAL`/`is_local = true`), então a conexão volta ao
   pool sem gabinete definido e não vaza para a próxima requisição.

O acesso do administrador a vários gabinetes (gabinete nulo) fica para a Etapa 3; hoje ele não vê
nada sob `lupa_app`.

## Revisão 0004 (Etapa 4C)

`pagina` ganha `sinais`, `coordenadas`, `extracao` (rota, OCR, divergência, tempo), `texto_nativo`,
`texto_ocr`, `versao_extrator`, `origem_arquivo` e `pagina_origem`; `job_ingestao` ganha
`relatorio` e `versao_extrator`; `diagnostico_arquivo` ganha `fronteiras_origem`, e o CHECK de
`cenario` aceita `pdf_com_bookmarks_e_indice`. Detalhes em `docs/ingestao.md`.

## Revisão 0006 (Etapa 4E)

`pagina` ganha `sinais_fronteira` (JSON). `peca` ganha `data`, `tipo_data` (CHECK:
`assinatura`, `protocolo`, `juntada`), `data_evidencia_id` (FK composta para `evidencia`, com o
literal da data, offsets e hash), `substitui_peca_id` (FK composta para a própria `peca`, que
passa a ter UNIQUE `(id, gabinete_id)`), `vigente` (padrão verdadeiro), `flags` e
`classificacao` (JSON), e o índice `(arquivo_id, vigente)`. A reclassificação manual nunca
altera a classificação de uma linha: grava linha nova `metodo = manual` que aponta a anterior e
só desliga `vigente` na anterior; o índice e a origem por trecho (4D.8) leem só as vigentes.

## Migrações

```bash
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api alembic -c src/lupa/migrations/alembic.ini downgrade base
```

A URL vem de `LUPA_DATABASE_URL`. O `alembic.ini` da raiz aponta para a mesma pasta, para uso fora
do contêiner. O `downgrade` remove tabelas e funções, mas mantém o papel `lupa_app`, que é global ao
cluster e pode estar em uso por outro database (por exemplo, o de testes).
