<script lang="ts">
  // Tela de auditoria (Etapa 6.9). Desembargador: só o próprio gabinete (a API resolve o
  // gabinete pela sessão). Administrador: escolhe o gabinete ou vê todos. Consulta com filtros
  // e paginação por cursor, exportação CSV/JSON, verificação da cadeia e relatório de uso com
  // custo estimado. Todo acesso a esta tela também é auditado pelo servidor.
  import { onMount } from 'svelte';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import {
    ACOES,
    apiAuditoria,
    FILTROS_VAZIOS,
    formatarDinheiro,
    formatarInstante,
    linkExportacao,
    textoVerificacao,
    validarFiltros,
    type EventoAuditoria,
    type Filtros,
    type RelatorioUso,
    type Verificacao,
  } from '$lib/auditoria/auditoria';
  import { sessao, tem } from '$lib/sessao.svelte';
  import type { Gabinete } from '$lib/tipos';

  const atual = $derived(sessao.atual);
  const ehAdmin = $derived(tem(atual, 'gerir_gabinetes'));
  const permitido = $derived(tem(atual, 'ver_auditoria'));

  let filtros = $state<Filtros>({ ...FILTROS_VAZIOS });
  let aplicados = $state<Filtros>({ ...FILTROS_VAZIOS });
  let gabinetes = $state<Gabinete[]>([]);
  let eventos = $state<EventoAuditoria[]>([]);
  let cursor = $state<string | null>(null);
  let consultando = $state(false);
  let consultado = $state(false);
  let tempoMs = $state<number | null>(null);
  let erro = $state('');
  let verificacao = $state<Verificacao | null>(null);
  let verificando = $state(false);
  let tipoRelatorio = $state<'processo' | 'usuario'>('processo');
  let idRelatorio = $state('');
  let relatorio = $state<RelatorioUso | null>(null);
  let erroRelatorio = $state('');

  async function consultar(mais = false): Promise<void> {
    erro = '';
    const invalido = validarFiltros(filtros);
    if (invalido) {
      erro = invalido;
      return;
    }
    consultando = true;
    const inicio = performance.now();
    try {
      if (!mais) aplicados = { ...filtros };
      const pagina = await apiAuditoria.consultar(aplicados, mais ? cursor : null);
      eventos = mais ? [...eventos, ...pagina.eventos] : pagina.eventos;
      cursor = pagina.proximo_cursor;
      tempoMs = Math.round(performance.now() - inicio);
      consultado = true;
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      consultando = false;
    }
  }

  onMount(() => {
    if (!permitido) return;
    if (ehAdmin) {
      chamar<Gabinete[]>('GET', '/gabinetes')
        .then((lista) => (gabinetes = lista))
        .catch((e: unknown) => (erro = mensagemErro(e)));
    }
    void consultar();
  });

  function enviar(evento: SubmitEvent): void {
    evento.preventDefault();
    void consultar();
  }

  function limpar(): void {
    filtros = { ...FILTROS_VAZIOS };
    void consultar();
  }

  async function verificar(): Promise<void> {
    verificando = true;
    verificacao = null;
    try {
      verificacao = await apiAuditoria.verificar(filtros.gabinete_id);
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      verificando = false;
    }
  }

  async function gerarRelatorio(evento?: SubmitEvent): Promise<void> {
    evento?.preventDefault();
    erroRelatorio = '';
    relatorio = null;
    const invalido = validarFiltros({
      ...FILTROS_VAZIOS,
      [tipoRelatorio === 'processo' ? 'processo_id' : 'usuario_id']: idRelatorio,
    });
    if (invalido || !idRelatorio.trim()) {
      erroRelatorio = invalido ?? 'Informe o identificador.';
      return;
    }
    try {
      relatorio = await apiAuditoria.relatorio(filtros.gabinete_id, tipoRelatorio, idRelatorio);
    } catch (e) {
      erroRelatorio = mensagemErro(e);
    }
  }

  function relatorioDe(tipo: 'processo' | 'usuario', id: string | null): void {
    if (!id) return;
    tipoRelatorio = tipo;
    idRelatorio = id;
    void gerarRelatorio();
    document.getElementById('titulo-relatorio')?.scrollIntoView();
  }

  function curto(id: string | null): string {
    return id ? id.slice(0, 8) : '—';
  }

  function nomeGabinete(id: string | null): string {
    if (id === null) return 'global';
    return gabinetes.find((g) => g.id === id)?.nome ?? curto(id);
  }
</script>

<svelte:head><title>Auditoria · Lupa</title></svelte:head>

<h1>Auditoria</h1>

{#if !permitido}
  <Aviso tipo="erro">Ação não permitida para o seu papel.</Aviso>
{:else}
  <p class="contexto">
    {ehAdmin
      ? 'Administrador: escolha um gabinete ou deixe em branco para ver todos.'
      : 'Você vê os eventos do seu gabinete.'}
  </p>
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}

  <form class="filtros" onsubmit={enviar} aria-label="Filtros da auditoria">
    {#if ehAdmin}
      <div>
        <label for="f-gabinete">Gabinete</label>
        <select id="f-gabinete" bind:value={filtros.gabinete_id}>
          <option value="">Todos</option>
          {#each gabinetes as g (g.id)}
            <option value={g.id}>{g.nome}</option>
          {/each}
        </select>
      </div>
    {/if}
    <div>
      <label for="f-usuario">Usuário (id)</label>
      <input id="f-usuario" bind:value={filtros.usuario_id} autocomplete="off" />
    </div>
    <div>
      <label for="f-processo">Processo (id)</label>
      <input id="f-processo" bind:value={filtros.processo_id} autocomplete="off" />
    </div>
    <div>
      <label for="f-acao">Ação</label>
      <select id="f-acao" bind:value={filtros.acao}>
        <option value="">Todas</option>
        {#each ACOES as acao (acao)}
          <option value={acao}>{acao}</option>
        {/each}
      </select>
    </div>
    <div>
      <label for="f-inicio">De</label>
      <input id="f-inicio" type="datetime-local" bind:value={filtros.inicio} />
    </div>
    <div>
      <label for="f-fim">Até</label>
      <input id="f-fim" type="datetime-local" bind:value={filtros.fim} />
    </div>
    <div>
      <label for="f-ip">IP</label>
      <input id="f-ip" bind:value={filtros.ip} maxlength="64" autocomplete="off" />
    </div>
    <div class="botoes">
      <button type="submit" disabled={consultando}>Consultar</button>
      <button type="button" class="secundario" onclick={limpar}>Limpar</button>
    </div>
  </form>

  <div class="barra">
    <span role="status" data-testid="tempo-consulta">
      {#if consultando}Consultando…{:else if tempoMs !== null}{eventos.length} evento(s) exibido(s);
        consulta respondida em {tempoMs} ms.{/if}
    </span>
    <span class="exportar">
      Exportar o filtro aplicado:
      <a href={linkExportacao(aplicados, 'csv')} download="auditoria.csv">CSV</a>
      <a href={linkExportacao(aplicados, 'json')} download="auditoria.json">JSON</a>
    </span>
  </div>

  {#if consultado}
    <table data-testid="tabela-eventos">
      <caption>Eventos, do mais recente ao mais antigo</caption>
      <thead>
        <tr>
          <th scope="col">Quando</th>
          <th scope="col">Ação</th>
          <th scope="col">Resultado</th>
          {#if ehAdmin}<th scope="col">Gabinete</th>{/if}
          <th scope="col">Usuário</th>
          <th scope="col">Processo</th>
          <th scope="col">Objeto</th>
          <th scope="col">IP</th>
          <th scope="col">Local</th>
        </tr>
      </thead>
      <tbody>
        {#each eventos as e (e.id)}
          <tr data-testid="evento" data-gabinete={e.gabinete_id ?? ''}>
            <td>{formatarInstante(e.ocorrido_em)}</td>
            <td>{e.acao}</td>
            <td>{e.resultado}</td>
            {#if ehAdmin}<td>{nomeGabinete(e.gabinete_id)}</td>{/if}
            <td>
              {#if e.usuario_id}
                <button
                  type="button"
                  class="link"
                  title={e.usuario_id}
                  aria-label={`Relatório de uso do usuário ${e.usuario_id}`}
                  onclick={() => relatorioDe('usuario', e.usuario_id)}>{curto(e.usuario_id)}</button
                >
              {:else}—{/if}
            </td>
            <td>
              {#if e.processo_id}
                <button
                  type="button"
                  class="link"
                  title={e.processo_id}
                  aria-label={`Relatório de uso do processo ${e.processo_id}`}
                  onclick={() => relatorioDe('processo', e.processo_id)}
                  >{curto(e.processo_id)}</button
                >
              {:else}—{/if}
            </td>
            <td>{e.objeto_tipo ?? '—'}</td>
            <td>{e.ip ?? '—'}</td>
            <td>{e.localizacao ?? '—'}</td>
          </tr>
        {:else}
          <tr><td colspan={ehAdmin ? 9 : 8}>Nenhum evento com esses filtros.</td></tr>
        {/each}
      </tbody>
    </table>
    {#if cursor}
      <button type="button" class="secundario" onclick={() => consultar(true)} disabled={consultando}>
        Carregar mais
      </button>
    {/if}
  {/if}

  <section aria-labelledby="titulo-verificacao">
    <h2 id="titulo-verificacao">Integridade da cadeia</h2>
    <p>
      Recalcula o hash de cada evento {ehAdmin && !filtros.gabinete_id
        ? 'da cadeia global (sem gabinete); escolha um gabinete para conferir a dele'
        : 'da cadeia do gabinete'}.
    </p>
    <button type="button" onclick={verificar} disabled={verificando}>
      {verificando ? 'Verificando…' : 'Verificar integridade'}
    </button>
    {#if verificacao}
      <div
        class="verificacao {verificacao.integra ? 'ok' : 'quebrada'}"
        role={verificacao.integra ? 'status' : 'alert'}
        data-testid="resultado-verificacao"
      >
        {textoVerificacao(verificacao)}
      </div>
    {/if}
  </section>

  <section aria-labelledby="titulo-relatorio">
    <h2 id="titulo-relatorio">Relatório de uso</h2>
    <form class="relatorio" onsubmit={gerarRelatorio}>
      <div>
        <label for="r-tipo">Por</label>
        <select id="r-tipo" bind:value={tipoRelatorio}>
          <option value="processo">Processo</option>
          <option value="usuario">Usuário</option>
        </select>
      </div>
      <div>
        <label for="r-id">Identificador</label>
        <input id="r-id" bind:value={idRelatorio} autocomplete="off" />
      </div>
      <div class="botoes"><button type="submit">Gerar relatório</button></div>
    </form>
    {#if erroRelatorio}<Aviso tipo="erro">{erroRelatorio}</Aviso>{/if}
    {#if relatorio}
      <div data-testid="relatorio-uso">
        <p>
          Primeiro acesso: {formatarInstante(relatorio.primeiro_acesso)} · Último acesso:
          {formatarInstante(relatorio.ultimo_acesso)}
        </p>
        <table>
          <caption>Eventos por ação</caption>
          <thead><tr><th scope="col">Ação</th><th scope="col">Total</th></tr></thead>
          <tbody>
            {#each Object.entries(relatorio.contagem_por_acao) as [acao, total] (acao)}
              <tr><td>{acao}</td><td>{total}</td></tr>
            {:else}
              <tr><td colspan="2">Sem eventos.</td></tr>
            {/each}
          </tbody>
        </table>
        {#if relatorio.chamadas_modelo.length > 0}
          <table>
            <caption>Chamadas ao modelo por versão</caption>
            <thead>
              <tr><th scope="col">Modelo</th><th scope="col">Prompt</th><th scope="col">Total</th></tr>
            </thead>
            <tbody>
              {#each relatorio.chamadas_modelo as c, i (i)}
                <tr><td>{c.versao_modelo ?? '—'}</td><td>{c.versao_prompt ?? '—'}</td><td>{c.total}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
        <div class="custo" data-testid="custo-estimado">
          <strong>
            Custo estimado: {formatarDinheiro(
              relatorio.custo_estimado.total,
              relatorio.custo_estimado.moeda,
            )}
          </strong>
          — {relatorio.custo_estimado.observacao}
          <br /><small>
            Tabela de preços versão {relatorio.custo_estimado.versao_tabela};
            fonte: {relatorio.custo_estimado.fonte}.
          </small>
          {#each relatorio.custo_estimado.por_modelo as m (m.modelo)}
            <br /><small>
              {m.modelo}: {m.tokens_entrada} tokens de entrada, {m.tokens_saida} de saída —
              {m.custo === null
                ? 'modelo fora da tabela de preços'
                : formatarDinheiro(m.custo, relatorio.custo_estimado.moeda)}
            </small>
          {/each}
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .contexto {
    color: var(--texto-suave);
    margin-top: 0;
  }
  .filtros,
  .relatorio {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
    gap: 0.75rem;
    align-items: end;
    margin-bottom: 1rem;
  }
  .botoes {
    display: flex;
    gap: 0.5rem;
  }
  .barra {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
  }
  .exportar a {
    margin-left: 0.5rem;
  }
  button.link {
    background: none;
    border: none;
    padding: 0;
    color: var(--primaria);
    text-decoration: underline;
    font-family: var(--mono);
    cursor: pointer;
  }
  .verificacao {
    margin-top: 0.75rem;
    padding: 0.6rem 0.8rem;
    border-radius: var(--raio);
    font-weight: 600;
  }
  .ok {
    background: var(--sucesso-fundo);
    color: var(--sucesso);
  }
  .quebrada {
    background: var(--perigo-fundo);
    color: var(--perigo);
  }
  .custo {
    margin-top: 0.75rem;
    padding: 0.6rem 0.8rem;
    background: var(--aviso-fundo);
    color: var(--aviso-texto);
    border-radius: var(--raio);
  }
</style>
