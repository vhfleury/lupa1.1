"""Testes da orquestração em paralelo (4C.8) e do relatório de qualidade (4C.10)."""

import threading
import time
from pathlib import Path
from typing import Any

from lupa.dominio.enums import MotivoFalha
from lupa.ingestao.extracao import (
    MODULO_EXTRATOR,
    FontePaginas,
    LimitadorGabinete,
    Paralelismo,
    Tarefa,
    executar_em_paralelo,
    executar_tarefa,
    linha_pagina,
    pendentes,
    planejar,
)
from lupa.ingestao.qualidade import para_saida_pipeline, relatorio_qualidade
from lupa.ingestao.sandbox import LimitesSandbox, ResultadoSandbox
from tests.ingestao.arquivos import pdf_texto

LIMITES = LimitesSandbox(memoria_mb=512, cpu_segundos=20, tempo_segundos=30)


def _fontes() -> list[FontePaginas]:
    return [
        FontePaginas(Path("a.pdf"), "001_a.pdf", 5, 0),
        FontePaginas(Path("b.pdf"), "002_b.pdf", 3, 5),
    ]


def _pagina(numero: int, **extra: Any) -> dict[str, Any]:
    return {"numero": numero, "tipo": "nativa", "texto": f"p{numero}", "rota": "nativa"} | extra


def test_planejamento_em_lotes_por_fonte_com_numeracao_continua() -> None:
    """Lotes não atravessam fontes; números contínuos no arquivo."""
    tarefas = planejar(_fontes(), 2)
    assert [(t.fonte.nome, t.inicio, t.fim) for t in tarefas] == [
        ("001_a.pdf", 1, 2), ("001_a.pdf", 3, 4), ("001_a.pdf", 5, 5), ("002_b.pdf", 1, 2),
        ("002_b.pdf", 3, 3),
    ]  # fmt: skip
    assert list(tarefas[3].numeros) == [6, 7]


def test_pendentes_pula_paginas_prontas_e_estreita_o_lote() -> None:
    """Lote completo some; lote parcial vira o intervalo que falta."""
    tarefas = planejar(_fontes(), 4)
    restantes = pendentes(tarefas, {1, 2, 3, 4, 6})
    assert [(t.fonte.nome, t.inicio, t.fim) for t in restantes] == [
        ("001_a.pdf", 5, 5),
        ("002_b.pdf", 2, 3),
    ]


def test_tarefa_converte_numeracao_e_falhas_do_filho() -> None:
    """Página do filho ganha número contínuo e origem; falha vira motivo."""
    tarefa = Tarefa(_fontes()[1], 1, 2)
    chamadas: list[tuple[str, list[str]]] = []

    def _ok(modulo: str, argumentos: list[str], _limites: LimitesSandbox) -> ResultadoSandbox:
        chamadas.append((modulo, argumentos))
        return ResultadoSandbox(dados={"ok": True, "paginas": [_pagina(1), _pagina(2)]})

    resultado = executar_tarefa(tarefa, LIMITES, _ok)
    assert chamadas == [(MODULO_EXTRATOR, ["b.pdf", "1", "2"])]
    assert [(p["numero"], p["pagina_origem"]) for p in resultado.paginas] == [(6, 1), (7, 2)]
    assert resultado.paginas[0]["origem_arquivo"] == "002_b.pdf"

    def _tempo(*_args: Any) -> ResultadoSandbox:
        return ResultadoSandbox(motivo_falha=MotivoFalha.TEMPO_ESGOTADO)

    def _recusa(*_args: Any) -> ResultadoSandbox:
        return ResultadoSandbox(dados={"ok": False, "erro": "abertura"})

    assert executar_tarefa(tarefa, LIMITES, _tempo).motivo_falha is MotivoFalha.TEMPO_ESGOTADO
    assert executar_tarefa(tarefa, LIMITES, _recusa).motivo_falha is MotivoFalha.ERRO_PARSER


def test_paralelismo_respeita_o_teto_do_gabinete() -> None:
    """Dois jobs do mesmo gabinete em paralelo nunca passam do teto somado."""
    ativos = 0
    pico = 0
    trava = threading.Lock()

    def _lento(*_args: Any) -> ResultadoSandbox:
        nonlocal ativos, pico
        with trava:
            ativos += 1
            pico = max(pico, ativos)
        time.sleep(0.05)
        with trava:
            ativos -= 1
        return ResultadoSandbox(dados={"ok": True, "paginas": []})

    limitador = LimitadorGabinete()
    paralelismo = Paralelismo(paginas_por_lote=1, lotes_por_job=4, lotes_por_gabinete=2)
    tarefas = planejar([FontePaginas(Path("a.pdf"), "a.pdf", 6, 0)], 1)

    def _job() -> None:
        list(
            executar_em_paralelo(
                tarefas, LIMITES, paralelismo, "g1", limitador=limitador, executor=_lento
            )
        )

    threads = [threading.Thread(target=_job) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert pico == 2


def test_lotes_reais_rodam_em_processos_filhos(tmp_path: Path) -> None:
    """Sandbox de verdade: PDF nativo em dois lotes paralelos."""
    caminho = tmp_path / "a.pdf"
    caminho.write_bytes(
        pdf_texto([f"Folha nativa {n} com texto suficiente aqui" for n in range(5)])
    )
    tarefas = planejar([FontePaginas(caminho, "a.pdf", 5, 0)], 3)
    resultados = list(
        executar_em_paralelo(
            tarefas, LIMITES, Paralelismo(3, 2, 2), "g", limitador=LimitadorGabinete()
        )
    )
    numeros = sorted(p["numero"] for r in resultados for p in r.paginas)
    assert numeros == [1, 2, 3, 4, 5]


def test_linha_de_pagina_e_relatorio_de_qualidade() -> None:
    """Contagens por tipo e rota, abstidas, flags, CER estimado, faltantes e tempo."""
    hibrida = _pagina(
        2,
        tipo="ocr",
        rota="abstencao",
        flags={"texto_divergente": True},
        ocr={"confianca_media": 80.0, "rotacao_correcao": 90},
        divergencia={"caracteres": 100, "distancia": 5},
        segundos=1.5,
    )
    linhas = [
        linha_pagina(_pagina(1, segundos=0.1, origem_arquivo="a.pdf", pagina_origem=1), "v"),
        linha_pagina(hibrida | {"origem_arquivo": "a.pdf", "pagina_origem": 2}, "v"),
    ]
    assert linhas[0]["versao_extrator"] == "v"
    relatorio = relatorio_qualidade(
        linhas,
        total_paginas=3,
        tempo_parede_segundos=2.0,
        falhas={"erro_ocr": 1},
        versao_extrator="v",
    )
    assert relatorio["por_tipo"] == {"nativa": 1, "ocr": 1, "vazia": 0}
    assert relatorio["abstidas"] == 1
    assert relatorio["flags"] == {"texto_divergente": 1}
    assert relatorio["cer_estimado"] == 0.05
    assert relatorio["paginas_faltando_lista"] == [3]
    assert relatorio["rotacoes_corrigidas"] == 1
    assert relatorio["tempo"]["por_mil_paginas"] == round(2.0 * 1000 / 3, 4)
    saida = para_saida_pipeline(linhas, 2.0)
    assert [p.ref.pagina for p in saida.paginas] == [1, 2]
    assert saida.pecas == () and saida.eventos == ()


def test_relatorio_sem_paginas_nao_divide_por_zero() -> None:
    """Arquivo sem páginas extraídas: taxas ausentes."""
    relatorio = relatorio_qualidade(
        [], total_paginas=0, tempo_parede_segundos=0.0, versao_extrator="v"
    )
    assert relatorio["cer_estimado"] is None
    assert relatorio["tempo"]["por_mil_paginas"] is None
