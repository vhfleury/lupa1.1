"""Testes do motor, catálogo, CLI, dados versionados e regras estruturais da Etapa 2."""

import ast
import json
import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from lupa.dominio.esquemas import Fato
from lupa.logging import configurar_logging
from lupa.validacoes import catalogo
from lupa.validacoes.__main__ import main
from lupa.validacoes.calendario import (
    Periodo,
    contar_prazo_corrido,
    contar_prazo_util,
    idade_em,
    somar_meses,
)
from lupa.validacoes.catalogo import Validacao, validacoes_de
from lupa.validacoes.dados import (
    ArquivoFeriados,
    ArquivoSuspensoes,
    FaixaArt109,
    ReducaoArt115,
    TabelaPrescricao,
    calendario_padrao,
    caminho_padrao,
    carregar,
    prazos_recursos_padrao,
    prescricao_padrao,
    preventiva_padrao,
)
from lupa.validacoes.modelo import AchadoValidacao, ConflitoDeFatosError, ModeloProcesso
from lupa.validacoes.motor import executar_catalogo
from tests.validacoes.conftest import criar_fato, id_sintetico, modelo_de

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "lupa" / "validacoes"
EXEMPLO = Path(__file__).with_name("fatos_exemplo.json")
EXEMPLO_DOCS = RAIZ / "docs" / "exemplos" / "fatos.json"
REFERENCIA = date(2026, 10, 20)
CONSTANTES_PERMITIDAS = {"_SABADO", "_DOMINGO", "_MESES_NO_ANO"}


def _modelo_exemplo() -> ModeloProcesso:
    dados = json.loads(EXEMPLO.read_text(encoding="utf-8"))
    return ModeloProcesso(Fato.model_validate(d) for d in dados)


def _datas_rastreaveis(valor: object) -> list[dict[str, object]]:
    if isinstance(valor, dict):
        proprias = [valor] if "data" in valor and "fato_id" in valor else []
        return proprias + [d for v in valor.values() for d in _datas_rastreaveis(v)]
    if isinstance(valor, list):
        return [d for v in valor for d in _datas_rastreaveis(v)]
    return []


def test_validacoes_sao_puras_mesma_entrada_mesmo_achado() -> None:
    """Validacoes sao puras mesma entrada mesmo achado."""
    modelo = _modelo_exemplo()
    primeira = [a.model_dump() for a in executar_catalogo(modelo, "criminal", REFERENCIA)]
    segunda = [a.model_dump() for a in executar_catalogo(modelo, "criminal", REFERENCIA)]
    assert primeira == segunda


def test_achados_conclusivos_trazem_datas_com_fato_e_evidencia() -> None:
    """Achados conclusivos trazem datas com fato e evidencia."""
    modelo = _modelo_exemplo()
    achados = executar_catalogo(modelo, "criminal", REFERENCIA)
    assert all(a.resultado in ("conforme", "atencao") for a in achados)
    ids_fatos = {str(f.id) for f in modelo.todos}
    for achado in achados:
        datas = _datas_rastreaveis(achado.valores)
        assert datas
        assert all(d["fato_id"] in ids_fatos and d["evidencia_id"] for d in datas)
        assert {d["fato_id"] for d in datas} <= {str(i) for i in achado.fatos_usados}


def test_motor_sobrevive_a_excecao_e_devolve_as_demais(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Motor sobrevive a excecao e devolve as demais."""

    def explode(modelo: ModeloProcesso, referencia: date) -> AchadoValidacao:
        raise RuntimeError("falha sintética")

    configurar_logging(estrito=True)
    quebrada = Validacao("quebrada", (), "nenhuma", explode)
    originais = catalogo.CATALOGO["criminal"]
    monkeypatch.setitem(catalogo.CATALOGO, "criminal", (quebrada, *originais))
    achados = executar_catalogo(_modelo_exemplo(), "criminal", REFERENCIA)
    assert len(achados) == len(originais) + 1
    assert achados[0].resultado == "verificar"
    assert achados[0].explicacao == (
        "A validação quebrada falhou ao executar (RuntimeError: falha sintética) e não produziu "
        "conclusão. Confira manualmente."
    )
    assert all(a.resultado != "verificar" for a in achados[1:])
    assert json.loads(capsys.readouterr().out)["erro_tipo"] == "RuntimeError"


def test_achado_grava_versao_do_catalogo() -> None:
    """AchadoValidacao grava versao do catalogo."""
    achados = executar_catalogo(_modelo_exemplo(), "criminal", REFERENCIA)
    assert {a.versao_catalogo for a in achados} == {catalogo.VERSAO_CATALOGO}


def test_catalogo_civel_existe_vazio_e_materia_desconhecida_falha() -> None:
    """Catalogo civel existe vazio e materia desconhecida falha."""
    assert validacoes_de("civel") == ()
    with pytest.raises(ValueError, match="matéria"):
        validacoes_de("trabalhista")


def test_cli_imprime_achados_do_exemplo(capsys: pytest.CaptureFixture[str]) -> None:
    """Cli imprime achados do exemplo."""
    codigo = main(["--fatos", str(EXEMPLO), "--materia", "criminal", "--referencia", "2026-10-20"])
    saida = json.loads(capsys.readouterr().out)
    assert codigo == 0
    assert [a["validacao"] for a in saida] == [v.nome for v in validacoes_de("criminal")]


def test_fato_sem_evidencia_e_rejeitado() -> None:
    """Fato sem evidencia e rejeitado."""
    base = criar_fato("data_fato", "2030-01-01").model_dump()
    with pytest.raises(ValidationError):
        Fato.model_validate({**base, "evidencias": []})


def test_modelo_aceita_repeticao_com_mesmo_valor_e_acusa_conflito() -> None:
    """Modelo aceita repeticao com mesmo valor e acusa conflito."""
    modelo = modelo_de(
        criar_fato("data_fato", "2030-01-01", fato_id="a"),
        criar_fato("data_fato", "2030-01-01", fato_id="b"),
        criar_fato("data_sentenca", "2030-01-01"),
        criar_fato("data_sentenca", "2030-02-01"),
    )
    fato = modelo.fato("data_fato")
    assert fato is not None and fato.id == min(id_sintetico("a"), id_sintetico("b"))
    assert modelo.fato("inexistente") is None
    with pytest.raises(ConflitoDeFatosError):
        modelo.fato("data_sentenca")


def test_modelo_recorta_por_reu() -> None:
    """Modelo recorta por reu."""
    modelo = modelo_de(
        criar_fato("data_fato", "2030-01-01"),
        criar_fato("data_nascimento_reu", {"valor": "2000-01-01", "reu_id": "r1"}),
        criar_fato("data_nascimento_reu", {"valor": "1950-01-01", "reu_id": "r2"}),
    )
    assert modelo.reus() == ["r1", "r2"]
    recorte = modelo.por_reu("r1")
    assert len(recorte.todos) == 2
    fato = recorte.fato("data_nascimento_reu")
    assert fato is not None and fato.valor["valor"] == "2000-01-01"


def test_prazo_util_pula_fim_de_semana_feriado_e_suspensao() -> None:
    """Prazo util pula fim de semana feriado e suspensao."""
    sexta = date(2030, 3, 1)
    resultado = contar_prazo_util(
        sexta,
        3,
        {date(2030, 3, 5): "feriado sintético"},
        [Periodo(date(2030, 3, 6), date(2030, 3, 6), "suspensão sintética")],
    )
    assert resultado.vencimento == date(2030, 3, 8)
    assert len(resultado.dias_suspensos) == 4


def test_prazo_corrido_sem_feriado_vence_no_dia_nominal() -> None:
    """Prazo corrido sem feriado vence no dia nominal."""
    resultado = contar_prazo_corrido(date(2030, 3, 4), 2, {}, [])
    assert resultado.vencimento == date(2030, 3, 6)


def test_somar_meses_e_idade() -> None:
    """Somar meses e idade."""
    assert somar_meses(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert somar_meses(date(2030, 11, 30), 3) == date(2031, 2, 28)
    assert idade_em(date(2000, 5, 10), date(2020, 5, 9)) == 19
    assert idade_em(date(2000, 5, 10), date(2020, 5, 10)) == 20


def test_dados_empacotados_tem_versao_e_fonte_e_sao_validos() -> None:
    """Dados empacotados tem versao e fonte e sao validos."""
    _, versoes = calendario_padrao()
    assert set(versoes) == {
        "feriados/nacionais.yaml",
        "feriados/tjgo.yaml",
        "suspensoes_prazo.yaml",
    }
    for tabela in (prazos_recursos_padrao(), prescricao_padrao(), preventiva_padrao()):
        assert tabela.versao and tabela.fonte


def test_todo_yaml_de_dados_exige_versao_e_fonte() -> None:
    """Todo yaml de dados exige versao e fonte."""
    arquivos = sorted((PACOTE / "dados").rglob("*.yaml"))
    assert len(arquivos) == 6
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        assert re.search(r"^versao:", texto, re.M) and re.search(r"^fonte:", texto, re.M)


def test_arquivo_sem_versao_e_rejeitado(tmp_path: Path) -> None:
    """Arquivo sem versao e rejeitado."""
    arquivo = tmp_path / "feriados.yaml"
    arquivo.write_text("fonte: x\nabrangencia: y\nferiados: []\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        carregar(arquivo, ArquivoFeriados)


def test_suspensao_com_fim_antes_do_inicio_e_rejeitada() -> None:
    """Suspensao com fim antes do inicio e rejeitada."""
    with pytest.raises(ValidationError):
        ArquivoSuspensoes.model_validate(
            {
                "versao": "1",
                "fonte": "sintética",
                "suspensoes": [
                    {
                        "inicio": "2030-01-10",
                        "fim": "2030-01-01",
                        "descricao": "x",
                        "base_legal": "y",
                    }
                ],
            }
        )


def test_tabela_de_prescricao_ambigua_falha() -> None:
    """Tabela de prescricao ambigua falha."""
    tabela = TabelaPrescricao(
        versao="1",
        fonte="sintética",
        base_legal="x",
        faixas=[FaixaArt109(inciso="A", prazo_anos=1), FaixaArt109(inciso="B", prazo_anos=2)],
        reducao=ReducaoArt115(
            idade_no_fato_abaixo_de=21, idade_na_sentenca_a_partir_de=70, divisor=2, base_legal="y"
        ),
    )
    with pytest.raises(ValueError, match="ambígua"):
        tabela.faixa_para(10)


def test_caminho_padrao_aponta_para_arquivo_existente() -> None:
    """Caminho padrao aponta para arquivo existente."""
    assert caminho_padrao("feriados/tjgo.yaml").is_file()


def _arquivos_py() -> list[Path]:
    return sorted(PACOTE.rglob("*.py"))


def test_nenhuma_validacao_importa_camadas_proibidas() -> None:
    """Nenhuma validacao importa camadas proibidas; do domínio, só esquemas e enums."""
    proibidos = ("lupa.dominio", "lupa.ingestao", "lupa.agente", "lupa.api")
    permitidos = {"lupa.dominio.esquemas", "lupa.dominio.enums"}
    for arquivo in _arquivos_py():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            nomes = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes = [no.module]
            assert not [
                n for n in nomes if n.startswith(proibidos) and n not in permitidos
            ], arquivo


def test_nenhum_numero_de_prazo_ou_data_em_arquivo_py() -> None:
    """Nenhum numero de prazo ou data em arquivo py."""
    for arquivo in _arquivos_py():
        texto = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"\d{4}-\d{2}-\d{2}", texto), arquivo
        arvore = ast.parse(texto)
        permitidos = {
            id(no.value)
            for no in ast.walk(arvore)
            if isinstance(no, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in CONSTANTES_PERMITIDAS for t in no.targets)
        }
        for no in ast.walk(arvore):
            if arquivo.name == "__main__.py":
                continue
            if isinstance(no, ast.Constant) and type(no.value) is int and no.value not in (0, 1):
                assert id(no) in permitidos, f"{arquivo}:{no.lineno}"


@pytest.mark.skipif(not EXEMPLO_DOCS.exists(), reason="docs/ não é copiado para a imagem")
def test_exemplo_da_documentacao_e_o_mesmo_dos_testes() -> None:
    """O fatos.json de docs/exemplos é idêntico ao usado nos testes."""
    assert EXEMPLO_DOCS.read_bytes() == EXEMPLO.read_bytes()
