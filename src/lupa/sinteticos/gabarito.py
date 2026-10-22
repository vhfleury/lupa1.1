"""Esquema versionado do gabarito de um processo sintético.

O gabarito descreve, para um arquivo gerado, o que uma ingestão perfeita deveria encontrar: as
peças (tipo, origem, páginas, data), cada página (tipo, composição, degradação, texto), os
eventos (tipo de fato, valor, página, trecho literal e offsets) e o resultado esperado das três
validações criminais. Páginas são numeradas pela folha de conteúdo (1 a N), igual nos três
cenários; ``arquivos`` diz em que arquivo e posição física cada folha ficou.
"""

from datetime import date
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lupa.dominio.cnj import validar_numero_cnj
from lupa.dominio.enums import (
    Materia,
    OrigemPeca,
    ResultadoAchado,
    TipoFato,
    TipoPagina,
    TipoPeca,
)

VERSAO_ESQUEMA = "1"
VALIDACOES_CRIMINAIS = ("tempestividade_recurso", "prescricao_abstrata", "revisao_preventiva")


class Cenario(StrEnum):
    """Forma de empacotamento do processo.

    Attributes:
        ZIP_POR_PECA: ZIP com um PDF por peça.
        PDF_INDICE: PDF único com bookmarks por peça e índice de movimentações no início.
        PDF_LISO: PDF único sem bookmarks nem índice.
    """

    ZIP_POR_PECA = "zip_por_peca"
    PDF_INDICE = "pdf_indice"
    PDF_LISO = "pdf_liso"


DIAGNOSTICO_ESPERADO = {
    Cenario.ZIP_POR_PECA: "zip_por_peca",
    Cenario.PDF_INDICE: "pdf_com_bookmarks_e_indice",
    Cenario.PDF_LISO: "pdf_liso",
}


class Composicao(StrEnum):
    """Como a página foi fabricada.

    Attributes:
        NATIVA: Todo o texto na camada de texto.
        DIGITALIZADA: Página inteira como imagem, sem camada de texto.
        HIBRIDA_CORPO: Cabeçalho e rodapé nativos; corpo em imagem.
        HIBRIDA_ASSINATURA: Texto nativo; bloco de assinatura em imagem.
        VAZIA: Página em branco.
        CAPA: Capa de autuação, nativa.
    """

    NATIVA = "nativa"
    DIGITALIZADA = "digitalizada"
    HIBRIDA_CORPO = "hibrida_corpo"
    HIBRIDA_ASSINATURA = "hibrida_assinatura"
    VAZIA = "vazia"
    CAPA = "capa"


TIPO_POR_COMPOSICAO = {
    Composicao.NATIVA: TipoPagina.NATIVA,
    Composicao.CAPA: TipoPagina.NATIVA,
    Composicao.DIGITALIZADA: TipoPagina.OCR,
    Composicao.HIBRIDA_CORPO: TipoPagina.OCR,
    Composicao.HIBRIDA_ASSINATURA: TipoPagina.OCR,
    Composicao.VAZIA: TipoPagina.VAZIA,
}
COM_IMAGEM = frozenset(
    {Composicao.DIGITALIZADA, Composicao.HIBRIDA_CORPO, Composicao.HIBRIDA_ASSINATURA}
)


class Degradacao(StrEnum):
    """Nível de degradação de imagem.

    Attributes:
        LEVE: Ruído baixo, até 1 grau, 300 DPI.
        MEDIA: Ruído médio, até 2 graus, 200 DPI.
        FORTE: Ruído alto, até 3 graus, 150 DPI, contraste baixo.
    """

    LEVE = "leve"
    MEDIA = "media"
    FORTE = "forte"


class TipoData(StrEnum):
    """O que a data da peça representa.

    Attributes:
        ASSINATURA: Data em que a peça foi assinada.
        PROTOCOLO: Data de protocolo pela parte.
        JUNTADA: Data de juntada aos autos.
    """

    ASSINATURA = "assinatura"
    PROTOCOLO = "protocolo"
    JUNTADA = "juntada"


class Elemento(StrEnum):
    """Elementos que atrapalham a leitura, marcados por página.

    Attributes:
        CARIMBO: Carimbo em imagem sobre o texto.
        MARCA_DAGUA: Marca d'água diagonal (texto na camada, ou na imagem se digitalizada).
        RODAPE_AUTENTICACAO: Rodapé com código de autenticação falso.
        CABECALHO_REPETIDO: Cabeçalho idêntico ao de outras peças.
        INJECAO: Página com tentativa de injeção.
        DUAS_COLUNAS: Corpo em duas colunas; ``texto`` traz a ordem de leitura (coluna da
            esquerda inteira, depois a da direita).
    """

    CARIMBO = "carimbo"
    MARCA_DAGUA = "marca_dagua"
    RODAPE_AUTENTICACAO = "rodape_autenticacao"
    CABECALHO_REPETIDO = "cabecalho_repetido"
    INJECAO = "injecao"
    DUAS_COLUNAS = "duas_colunas"


class VetorInjecao(StrEnum):
    """Vetor da injeção (``prompt-injection.md``, seção 1).

    Attributes:
        TEXTO_BRANCO: Texto branco em fonte de 1 pt.
        FORA_DA_PAGINA: Texto posicionado fora da área visível.
        METADADO_XMP: Instrução nos metadados XMP.
        ANOTACAO: Instrução em anotação do PDF.
        IMAGEM_COM_TEXTO: Instrução escrita dentro de imagem.
        BASE64: Instrução codificada em base64.
        HOMOGLIFOS: Instrução com letras cirílicas parecidas com latinas.
        IDIOMA_ALTERNADO: Parágrafo em inglês dentro das razões.
        TRANSCRICAO_CITADA: Instrução dentro de mensagem transcrita em laudo.
    """

    TEXTO_BRANCO = "texto_branco"
    FORA_DA_PAGINA = "fora_da_pagina"
    METADADO_XMP = "metadado_xmp"
    ANOTACAO = "anotacao"
    IMAGEM_COM_TEXTO = "imagem_com_texto"
    BASE64 = "base64"
    HOMOGLIFOS = "homoglifos"
    IDIOMA_ALTERNADO = "idioma_alternado"
    TRANSCRICAO_CITADA = "transcricao_citada"


TODOS_VETORES: tuple[VetorInjecao, ...] = tuple(VetorInjecao.__members__.values())


class ObjetivoInjecao(StrEnum):
    """O que a injeção tenta obter.

    Attributes:
        SUPRIMIR_ACHADO: Esconder um achado de atenção.
        CRIAR_ACHADO: Produzir achado inexistente.
        VAZAR_DADO: Extrair dado de outro processo ou do sistema.
        ALTERAR_DATA: Fazer o sistema adotar data falsa.
        MUDAR_CLASSIFICACAO: Mudar o tipo de uma peça.
    """

    SUPRIMIR_ACHADO = "suprimir_achado"
    CRIAR_ACHADO = "criar_achado"
    VAZAR_DADO = "vazar_dado"
    ALTERAR_DATA = "alterar_data"
    MUDAR_CLASSIFICACAO = "mudar_classificacao"


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProcessoGabarito(_Base):
    """Identificação do processo sintético e do cenário."""

    numero_cnj: str
    materia: Materia = Materia.CRIMINAL
    cenario: Cenario
    diagnostico_esperado: str
    semente: int
    data_referencia: date

    @field_validator("numero_cnj")
    @classmethod
    def _cnj(cls, valor: str) -> str:
        return validar_numero_cnj(valor)

    @model_validator(mode="after")
    def _diagnostico(self) -> Self:
        if self.diagnostico_esperado != DIAGNOSTICO_ESPERADO[self.cenario]:
            raise ValueError("diagnóstico esperado não corresponde ao cenário")
        return self


class PecaGabarito(_Base):
    """Peça processual e as folhas que ocupa."""

    indice: int = Field(ge=1)
    tipo: TipoPeca
    origem: OrigemPeca
    titulo: str = Field(min_length=1)
    pagina_inicial: int = Field(ge=1)
    pagina_final: int = Field(ge=1)
    data: date
    tipo_data: TipoData

    @model_validator(mode="after")
    def _intervalo(self) -> Self:
        if self.pagina_final < self.pagina_inicial:
            raise ValueError("página final anterior à inicial")
        return self


class PaginaGabarito(_Base):
    """Folha de conteúdo: tipo esperado, como foi fabricada e o texto.

    ``texto`` é o texto visível (o que um OCR perfeito leria, sem o texto de carimbos, da marca
    d'água e de imagens decorativas); ``texto_camada`` é exatamente o que ``page.get_text()``
    devolve. Offsets de eventos referem-se a ``texto``.
    """

    numero: int = Field(ge=1)
    peca: int = Field(ge=1)
    tipo: TipoPagina
    composicao: Composicao
    degradacao: Degradacao | None = None
    dpi: int | None = None
    rotacao_graus: float | None = None
    elementos: tuple[Elemento, ...] = ()
    texto: str
    texto_camada: str

    @model_validator(mode="after")
    def _coerente(self) -> Self:
        if TIPO_POR_COMPOSICAO[self.composicao] != self.tipo:
            raise ValueError("tipo de página incompatível com a composição")
        if (self.composicao in COM_IMAGEM) != (self.degradacao is not None):
            raise ValueError("degradação exigida só e sempre para páginas com imagem")
        if self.composicao == Composicao.VAZIA and (self.texto or self.texto_camada):
            raise ValueError("página vazia com texto")
        if self.composicao == Composicao.DIGITALIZADA and self.texto_camada:
            raise ValueError("página digitalizada com camada de texto")
        return self


class EventoGabarito(_Base):
    """Fato que a extração deve encontrar, com a evidência literal."""

    tipo: TipoFato
    valor: Any
    pagina: int = Field(ge=1)
    trecho: str = Field(min_length=1)
    inicio: int = Field(ge=0)
    fim: int = Field(ge=1)

    @model_validator(mode="after")
    def _offsets(self) -> Self:
        if self.fim - self.inicio != len(self.trecho):
            raise ValueError("offsets não correspondem ao tamanho do trecho")
        return self


class ResultadoEsperado(_Base):
    """Resultado que o motor de validações deve dar com os eventos do gabarito."""

    validacao: str
    resultado: ResultadoAchado
    valores: dict[str, Any]
    explicacao: str


class ArquivoGabarito(_Base):
    """Arquivo físico do cenário; ``folhas[i]`` é a folha de conteúdo da página física i+1.

    ``None`` marca páginas que não são conteúdo (índice de movimentações).
    """

    nome: str = Field(min_length=1)
    folhas: tuple[int | None, ...]


class InjecaoGabarito(_Base):
    """Tentativa de injeção plantada no processo."""

    vetor: VetorInjecao
    objetivo: ObjetivoInjecao
    pagina: int | None
    texto: str = Field(min_length=1)
    visivel: bool


class Gabarito(_Base):
    """Gabarito completo de um arquivo sintético."""

    versao_esquema: str = VERSAO_ESQUEMA
    processo: ProcessoGabarito
    pecas: tuple[PecaGabarito, ...] = Field(min_length=1)
    paginas: tuple[PaginaGabarito, ...] = Field(min_length=1)
    eventos: tuple[EventoGabarito, ...]
    resultado_esperado: tuple[ResultadoEsperado, ...]
    arquivos: tuple[ArquivoGabarito, ...] = Field(min_length=1)
    injecoes: tuple[InjecaoGabarito, ...] = ()

    @model_validator(mode="after")
    def _consistente(self) -> Self:
        if self.versao_esquema != VERSAO_ESQUEMA:
            raise ValueError("versão de esquema desconhecida")
        self._conferir_paginas()
        self._conferir_pecas()
        self._conferir_eventos()
        self._conferir_arquivos()
        nomes = sorted(r.validacao for r in self.resultado_esperado)
        if nomes != sorted(VALIDACOES_CRIMINAIS):
            raise ValueError("resultado esperado deve cobrir as três validações criminais")
        return self

    def _conferir_paginas(self) -> None:
        if [p.numero for p in self.paginas] != list(range(1, len(self.paginas) + 1)):
            raise ValueError("páginas devem ser numeradas de 1 a N, em ordem")

    def _conferir_pecas(self) -> None:
        esperado = 1
        for posicao, peca in enumerate(self.pecas, start=1):
            if peca.indice != posicao or peca.pagina_inicial != esperado:
                raise ValueError("peças devem ser contíguas, em ordem e sem sobreposição")
            esperado = peca.pagina_final + 1
            for numero in range(peca.pagina_inicial, peca.pagina_final + 1):
                if numero > len(self.paginas) or self.paginas[numero - 1].peca != peca.indice:
                    raise ValueError("página não pertence à peça indicada")
        if esperado != len(self.paginas) + 1:
            raise ValueError("peças não cobrem todas as páginas")

    def _conferir_eventos(self) -> None:
        for evento in self.eventos:
            if evento.pagina > len(self.paginas):
                raise ValueError("evento aponta para página inexistente")
            texto = self.paginas[evento.pagina - 1].texto
            if texto[evento.inicio : evento.fim] != evento.trecho:
                raise ValueError("trecho do evento não está nos offsets da página")

    def _conferir_arquivos(self) -> None:
        folhas = sorted(f for a in self.arquivos for f in a.folhas if f is not None)
        if folhas != list(range(1, len(self.paginas) + 1)):
            raise ValueError("arquivos devem conter cada folha exatamente uma vez")

    def pagina(self, numero: int) -> PaginaGabarito:
        """Devolve a folha de conteúdo pelo número.

        Args:
            numero: Número da folha (1 a N).

        Returns:
            A página.
        """
        return self.paginas[numero - 1]
