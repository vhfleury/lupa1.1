"""Enumerações do domínio jurídico do Lupa."""

from enum import StrEnum


class Materia(StrEnum):
    """Matéria do processo.

    Attributes:
        CRIMINAL: Processo penal; regido pelo CPP e CP.
        CIVEL: Processo cível; regido pelo CPC.
    """

    CRIMINAL = "criminal"
    CIVEL = "civel"


class StatusProcesso(StrEnum):
    """Situação do processo dentro do Lupa.

    Attributes:
        CRIADO: Cadastrado, sem arquivos processados.
        EM_INGESTAO: Arquivos sendo processados.
        PRONTO: Fatos extraídos e validações disponíveis.
        BLOQUEADO: Ingestão recusada (por exemplo, processo sigiloso na v1).
        ARQUIVADO: Fora de uso; mantido para auditoria.
        EM_REVISAO: Incidente de injeção no agente; relatório e chat bloqueados até um
            desembargador ou administrador liberar (Etapa 6.8).
        DESCARTADO: Exclusão criptográfica (Etapa 7.7): DEK apagada, só resta o registro.
    """

    CRIADO = "criado"
    EM_INGESTAO = "em_ingestao"
    PRONTO = "pronto"
    BLOQUEADO = "bloqueado"
    ARQUIVADO = "arquivado"
    EM_REVISAO = "em_revisao"
    DESCARTADO = "descartado"


class TipoPeca(StrEnum):
    """Tipo de peça processual; extensível acrescentando valores.

    Attributes:
        DENUNCIA: Denúncia do Ministério Público.
        RECEBIMENTO: Decisão de recebimento da denúncia.
        DECISAO_PRISAO: Decisão que decreta ou revisa prisão.
        SENTENCA: Sentença.
        CERTIDAO: Certidão cartorária (intimação, publicação, trânsito).
        RECURSO: Petição de recurso.
        CONTRARRAZOES: Contrarrazões de recurso.
        ACORDAO: Acórdão.
        LAUDO: Laudo pericial.
        TERMO_DEPOIMENTO: Termo de depoimento ou interrogatório.
        OUTROS: Peça não classificada.
    """

    DENUNCIA = "denuncia"
    RECEBIMENTO = "recebimento"
    DECISAO_PRISAO = "decisao_prisao"
    SENTENCA = "sentenca"
    CERTIDAO = "certidao"
    RECURSO = "recurso"
    CONTRARRAZOES = "contrarrazoes"
    ACORDAO = "acordao"
    LAUDO = "laudo"
    TERMO_DEPOIMENTO = "termo_depoimento"
    OUTROS = "outros"


class MetodoClassificacao(StrEnum):
    """Como a peça foi identificada.

    Attributes:
        REGRA: Por regra determinística.
        LLM: Por modelo de linguagem.
        MANUAL: Por pessoa.
    """

    REGRA = "regra"
    LLM = "llm"
    MANUAL = "manual"


class OrigemPeca(StrEnum):
    """Quem produziu a peça.

    Attributes:
        JUIZO: O juízo ou a secretaria.
        MP: O Ministério Público.
        DEFESA: A defesa.
        TERCEIRO: Terceiro (perito, testemunha, outro órgão).
        DESCONHECIDA: Não identificada.
    """

    JUIZO = "juizo"
    MP = "mp"
    DEFESA = "defesa"
    TERCEIRO = "terceiro"
    DESCONHECIDA = "desconhecida"


class TipoPagina(StrEnum):
    """Origem do texto da página.

    Attributes:
        NATIVA: Texto extraído da camada de texto do PDF.
        OCR: Texto obtido por reconhecimento óptico.
        VAZIA: Página sem texto.
    """

    NATIVA = "nativa"
    OCR = "ocr"
    VAZIA = "vazia"


class FlagPagina(StrEnum):
    """Marcadores de ingestão definidos em `prompt-injection.md`.

    Attributes:
        TEXTO_OCULTO: Texto invisível (cor, tamanho ou posição).
        BLOCO_CODIFICADO: Bloco em base64 ou codificação semelhante.
        PADRAO_INSTRUCAO: Texto com forma de instrução a um modelo.
        IDIOMA_INESPERADO: Trecho em idioma diferente do esperado.
        TEXTO_DIVERGENTE: Camada de texto diverge do que o OCR lê na imagem da página.
        METADADO_SUSPEITO: Metadado, anotação ou campo do PDF com padrão de instrução.
        HOMOGLIFOS: Texto com caracteres de outros alfabetos trocados pelo latino.
        DENSIDADE_ANOMALA: Volume de texto muito acima do padrão do tipo de página.
    """

    TEXTO_OCULTO = "texto_oculto"
    BLOCO_CODIFICADO = "bloco_codificado"
    PADRAO_INSTRUCAO = "padrao_instrucao"
    IDIOMA_INESPERADO = "idioma_inesperado"
    TEXTO_DIVERGENTE = "texto_divergente"
    METADADO_SUSPEITO = "metadado_suspeito"
    HOMOGLIFOS = "homoglifos"
    DENSIDADE_ANOMALA = "densidade_anomala"


class TipoFato(StrEnum):
    """Tipos iniciais de fato extraído dos autos.

    Attributes:
        DATA_FATO: Data do fato criminoso.
        DATA_DENUNCIA: Data de oferecimento da denúncia.
        DATA_RECEBIMENTO_DENUNCIA: Data do recebimento da denúncia (marco do art. 117, I, CP).
        DATA_SENTENCA: Data da sentença.
        DATA_PUBLICACAO_SENTENCA: Data de publicação da sentença (marco do art. 117, IV, CP).
        DATA_INTIMACAO_DEFESA: Data de intimação do defensor.
        DATA_INTIMACAO_MP: Data de intimação do Ministério Público.
        DATA_INTIMACAO_REU: Data de intimação pessoal do réu.
        DATA_INTERPOSICAO_RECURSO: Data de interposição do recurso.
        TIPO_RECURSO: Espécie do recurso interposto.
        DATA_DECRETACAO_PREVENTIVA: Data da decretação da prisão preventiva.
        DATA_REVISAO_PREVENTIVA: Data de cada revisão da preventiva (art. 316 CPP).
        PENA_MAXIMA_ABSTRATA: Pena máxima em abstrato, em meses.
        DATA_NASCIMENTO_REU: Data de nascimento do réu (art. 115 CP).
        REINCIDENTE: Se o réu é reincidente.
    """

    DATA_FATO = "data_fato"
    DATA_DENUNCIA = "data_denuncia"
    DATA_RECEBIMENTO_DENUNCIA = "data_recebimento_denuncia"
    DATA_SENTENCA = "data_sentenca"
    DATA_PUBLICACAO_SENTENCA = "data_publicacao_sentenca"
    DATA_INTIMACAO_DEFESA = "data_intimacao_defesa"
    DATA_INTIMACAO_MP = "data_intimacao_mp"
    DATA_INTIMACAO_REU = "data_intimacao_reu"
    DATA_INTERPOSICAO_RECURSO = "data_interposicao_recurso"
    TIPO_RECURSO = "tipo_recurso"
    DATA_DECRETACAO_PREVENTIVA = "data_decretacao_preventiva"
    DATA_REVISAO_PREVENTIVA = "data_revisao_preventiva"
    PENA_MAXIMA_ABSTRATA = "pena_maxima_abstrata"
    DATA_NASCIMENTO_REU = "data_nascimento_reu"
    REINCIDENTE = "reincidente"


class StatusFato(StrEnum):
    """Estado de revisão humana de um fato.

    Attributes:
        AUTOMATICO: Extraído pelo sistema, sem revisão.
        CONFIRMADO: Conferido e mantido por pessoa.
        CORRIGIDO: Novo fato que substitui outro após correção humana.
    """

    AUTOMATICO = "automatico"
    CONFIRMADO = "confirmado"
    CORRIGIDO = "corrigido"


class ResultadoAchado(StrEnum):
    """Resultado de uma validação.

    Attributes:
        CONFORME: A regra foi atendida.
        ATENCAO: A regra indica problema (por exemplo, intempestivo ou prescrito).
        VERIFICAR: Faltam fatos ou há conflito; exige conferência humana.
    """

    CONFORME = "conforme"
    ATENCAO = "atencao"
    VERIFICAR = "verificar"


class PapelUsuario(StrEnum):
    """Papel de acesso (detalhado na Etapa 3).

    Attributes:
        ASSESSOR: Acessa processos do próprio gabinete.
        DESEMBARGADOR: Assessor mais auditoria e gestão do gabinete.
        ADMINISTRADOR: Visão de todos os gabinetes; sem gabinete próprio.
    """

    ASSESSOR = "assessor"
    DESEMBARGADOR = "desembargador"
    ADMINISTRADOR = "administrador"


class EstadoJob(StrEnum):
    """Estado de um job de ingestão; as transições válidas ficam em `lupa.ingestao.estados`.

    Attributes:
        RECEBIDO: Arquivo lacrado e gravado no storage; aguardando validação.
        VALIDADO: Estrutura conferida (tipo, integridade, inventário); pronto para extração.
        EM_EXTRACAO: Páginas sendo extraídas.
        PARCIAL: Extração interrompida com parte das páginas gravadas.
        EM_REVISAO: Extração concluída com pendências para o assessor.
        CONCLUIDO: Ingestão terminada; estado final.
        FALHO: Erro de processamento (limite de recurso, erro interno); pode ser refeito.
        QUARENTENA: Arquivo recusado por motivo enumerado; estado final, nada avança.
    """

    RECEBIDO = "recebido"
    VALIDADO = "validado"
    EM_EXTRACAO = "em_extracao"
    PARCIAL = "parcial"
    EM_REVISAO = "em_revisao"
    CONCLUIDO = "concluido"
    FALHO = "falho"
    QUARENTENA = "quarentena"


class MotivoQuarentena(StrEnum):
    """Motivo pelo qual um arquivo foi posto em quarentena.

    Attributes:
        CORROMPIDO: Estrutura ilegível (PDF que não abre, ZIP com CRC errado).
        SENHA: Arquivo ou entrada protegido por senha.
        TRUNCADO: PDF sem o marcador final `%%EOF`.
        ASSINATURA_INVALIDA: `/ByteRange` de assinatura que não cobre o arquivo inteiro.
        TIPO_INVALIDO: Conteúdo que não é PDF (ou entrada de ZIP que não é PDF).
        ZIP_MALICIOSO: Caminho perigoso, link simbólico ou limites de ZIP excedidos.
    """

    CORROMPIDO = "corrompido"
    SENHA = "senha"
    TRUNCADO = "truncado"
    ASSINATURA_INVALIDA = "assinatura_invalida"
    TIPO_INVALIDO = "tipo_invalido"
    ZIP_MALICIOSO = "zip_malicioso"


class MotivoFalha(StrEnum):
    """Motivo de um job `falho`.

    Attributes:
        LIMITE_MEMORIA: O parser excedeu o limite de memória do sandbox.
        LIMITE_CPU: O parser excedeu o limite de CPU do sandbox.
        TEMPO_ESGOTADO: O parser excedeu o tempo de parede do sandbox.
        ERRO_PARSER: O parser terminou com erro ou saída ilegível.
        ARQUIVO_AUSENTE: O objeto não está no storage.
        ERRO_INTERNO: Erro inesperado do worker.
    """

    LIMITE_MEMORIA = "limite_memoria"
    LIMITE_CPU = "limite_cpu"
    TEMPO_ESGOTADO = "tempo_esgotado"
    ERRO_PARSER = "erro_parser"
    ARQUIVO_AUSENTE = "arquivo_ausente"
    ERRO_INTERNO = "erro_interno"


class CenarioArquivo(StrEnum):
    """Cenário de empacotamento diagnosticado (preenchido pela Etapa 4C).

    Attributes:
        ZIP_POR_PECA: ZIP com um PDF por peça.
        PDF_COM_BOOKMARKS: PDF único com bookmarks.
        PDF_COM_INDICE: PDF único com índice de movimentações no texto.
        PDF_LISO: PDF único sem bookmarks nem índice.
        PDF_COM_BOOKMARKS_E_INDICE: PDF único com bookmarks e índice de movimentações.
    """

    ZIP_POR_PECA = "zip_por_peca"
    PDF_COM_BOOKMARKS = "pdf_com_bookmarks"
    PDF_COM_INDICE = "pdf_com_indice"
    PDF_LISO = "pdf_liso"
    PDF_COM_BOOKMARKS_E_INDICE = "pdf_com_bookmarks_e_indice"


class EstadoLote(StrEnum):
    """Estado de um lote de trabalho de um job.

    Attributes:
        CONCLUIDO: Resultado gravado.
        FALHO: O lote terminou com falha registrada.
    """

    CONCLUIDO = "concluido"
    FALHO = "falho"


class PapelMensagem(StrEnum):
    """Autor de uma mensagem do chat (Etapa 5).

    Attributes:
        USUARIO: Pergunta do assessor.
        AGENTE: Resposta do agente (ou recusa, ou aviso de teto).
    """

    USUARIO = "usuario"
    AGENTE = "agente"


class StatusMensagem(StrEnum):
    """Desfecho de uma mensagem do chat (Etapa 5).

    Attributes:
        PERGUNTA: Pergunta registrada.
        RESPONDIDA: Resposta com ao menos uma citação conferida.
        SEM_EVIDENCIA: Resposta sem nenhuma citação válida (exibida com aviso).
        RECUSA: Pergunta fora do escopo; o agente explica o limite.
        DESCARTADA: Saída do modelo descartada (esquema, instrução refletida, outro processo).
        TETO: Teto de tokens atingido; a conversa foi encerrada.
    """

    PERGUNTA = "pergunta"
    RESPONDIDA = "respondida"
    SEM_EVIDENCIA = "sem_evidencia"
    RECUSA = "recusa"
    DESCARTADA = "descartada"
    TETO = "teto"


class ResultadoChamada(StrEnum):
    """Desfecho de uma chamada ao modelo (Etapa 5).

    Attributes:
        OK: Saída válida.
        INVALIDA: Saída fora do esquema.
        BLOQUEADA: Saída descartada por instrução refletida ou dado de outro processo.
        TETO: Chamada acima do teto de tokens por chamada.
        ERRO: Falha do cliente ou da API.
    """

    OK = "ok"
    INVALIDA = "invalida"
    BLOQUEADA = "bloqueada"
    TETO = "teto"
    ERRO = "erro"
