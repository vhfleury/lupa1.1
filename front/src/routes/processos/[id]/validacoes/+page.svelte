<script lang="ts">
  // Validações: achados vigentes com resultado, valores completos (datas com link para a página
  // e a evidência), explicação, fatos usados (confirmar ou corrigir), anotações e histórico.
  // Corrigir grava um fato NOVO ligado ao original; os achados antigos continuam no histórico.
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import {
    datasDosValores,
    DATA_ISO,
    formatarData,
    legivel,
    RESULTADO,
    STATUS_FATO,
    textoDoValor,
    valorDoFato,
  } from '$lib/processos/rotulos';
  import type { Achado, Anotacao, Fato } from '$lib/processos/tipos';
  import { sessao, tem } from '$lib/sessao.svelte';

  const id = $derived(page.params['id'] ?? '');
  let achados = $state<Achado[]>([]);
  let historico = $state<Achado[]>([]);
  let fatos = $state<Fato[]>([]);
  let anotacoes = $state<Anotacao[]>([]);
  let erro = $state('');
  let aviso = $state('');
  let carregando = $state(true);
  let editando = $state<string | null>(null);
  let valorNovo = $state('');
  let anotandoEm = $state<string | null>(null);
  let textoNota = $state('');

  const podeAnotar = $derived(tem(sessao.atual, 'anotar'));
  const porId = $derived(new Map(fatos.map((f) => [f.id, f])));
  const antigos = $derived(historico.filter((a) => !a.vigente));
  const substituidos = $derived(fatos.filter((f) => !f.vigente));

  async function carregar(): Promise<void> {
    try {
      const [v, h, f, n] = await Promise.all([
        chamar<{ achados: Achado[] }>('GET', `/processos/${id}/achados`),
        chamar<{ achados: Achado[] }>('GET', `/processos/${id}/achados/historico`),
        chamar<{ fatos: Fato[] }>('GET', `/processos/${id}/fatos`),
        chamar<{ anotacoes: Anotacao[] }>('GET', `/processos/${id}/anotacoes`),
      ]);
      achados = v.achados;
      historico = h.achados;
      fatos = f.fatos;
      anotacoes = n.anotacoes;
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      carregando = false;
    }
  }

  onMount(() => void carregar());

  function linkEvidencia(fato: Fato): string | null {
    const evidencia = fato.evidencias[0];
    return evidencia ? `/processos/${id}/visualizador?evidencia=${evidencia.id}` : null;
  }

  /** Fato usado pelo achado cujo valor é a data (para o link da página). */
  function fatoDaData(achado: Achado, data: string): Fato | undefined {
    return achado.fatos_usados
      .map((fid) => porId.get(fid))
      .find((f) => f !== undefined && valorDoFato(f.valor) === data);
  }

  function notasDe(alvo: { achado?: string; fato?: string }): Anotacao[] {
    return anotacoes.filter((a) => (alvo.achado ? a.achado_id === alvo.achado : a.fato_id === alvo.fato));
  }

  function iniciarCorrecao(fato: Fato): void {
    editando = fato.id;
    const valor = valorDoFato(fato.valor);
    valorNovo = typeof valor === 'string' ? valor : JSON.stringify(valor);
  }

  function interpretar(fato: Fato, texto: string): unknown {
    const original = valorDoFato(fato.valor);
    if (typeof original === 'string') return texto.trim();
    try {
      return JSON.parse(texto) as unknown;
    } catch {
      return texto.trim();
    }
  }

  async function registrar(fato: Fato, status: 'confirmado' | 'corrigido'): Promise<void> {
    erro = '';
    aviso = '';
    const corpo: Record<string, unknown> = { status };
    if (status === 'corrigido') corpo['valor'] = interpretar(fato, valorNovo);
    try {
      const r = await chamar<{ achados_gravados: number }>(
        'POST',
        `/processos/${id}/fatos/${fato.id}/corrigir`,
        corpo,
      );
      aviso =
        status === 'corrigido'
          ? `Fato corrigido. Validações reexecutadas: ${r.achados_gravados} achado(s) novo(s); os anteriores ficam no histórico.`
          : 'Fato confirmado.';
      editando = null;
      await carregar();
    } catch (e) {
      erro = mensagemErro(e);
    }
  }

  async function anotar(alvo: { achado_id?: string; fato_id?: string }): Promise<void> {
    erro = '';
    if (!textoNota.trim()) return;
    try {
      await chamar('POST', `/processos/${id}/anotacoes`, { ...alvo, texto: textoNota.trim() });
      textoNota = '';
      anotandoEm = null;
      aviso = 'Anotação registrada.';
      await carregar();
    } catch (e) {
      erro = mensagemErro(e);
    }
  }
</script>

<svelte:head><title>Validações · Lupa</title></svelte:head>

<p><a href="/processos/{id}">← Processo</a></p>
<h1>Validações</h1>
{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
{#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

{#snippet notas(lista: Anotacao[])}
  {#if lista.length}
    <ul class="notas">
      {#each lista as n (n.id)}
        <li><strong>{n.autor ?? 'usuário'}</strong> ({formatarData(n.criado_em)}): {n.texto}</li>
      {/each}
    </ul>
  {/if}
{/snippet}

{#snippet formNota(chave: string, alvo: { achado_id?: string; fato_id?: string })}
  {#if podeAnotar}
    {#if anotandoEm === chave}
      <form
        class="nota"
        onsubmit={(e) => {
          e.preventDefault();
          void anotar(alvo);
        }}
      >
        <label for="nota-{chave}">Anotação</label>
        <textarea id="nota-{chave}" bind:value={textoNota} maxlength="2000" rows="2"></textarea>
        <button type="submit">Salvar anotação</button>
        <button type="button" class="secundario" onclick={() => (anotandoEm = null)}>Cancelar</button>
      </form>
    {:else}
      <button type="button" class="secundario" onclick={() => ((anotandoEm = chave), (textoNota = ''))}>Anotar</button>
    {/if}
  {/if}
{/snippet}

{#if carregando}
  <p role="status">Carregando…</p>
{:else if achados.length === 0}
  <p class="dica">Nenhum achado ainda. Os achados aparecem quando a ingestão termina.</p>
{:else}
  {#each achados as a (a.id)}
    <article class="cartao achado {a.resultado}" data-testid="achado" data-validacao={a.validacao}>
      <header>
        <h2>{legivel(a.validacao)}</h2>
        <span class="resultado {a.resultado}" data-testid="resultado">{RESULTADO[a.resultado] ?? a.resultado}</span>
      </header>
      <p>{a.explicacao}</p>
      <h3>Valores</h3>
      <dl class="valores">
        {#each Object.entries(a.valores) as [chave, valor] (chave)}
          <dt>{legivel(chave)}</dt>
          <dd>
            {#if typeof valor === 'string' && DATA_ISO.test(valor)}
              {@const fato = fatoDaData(a, valor)}
              {#if fato && linkEvidencia(fato)}
                <a href={linkEvidencia(fato)} data-testid="link-data">{formatarData(valor)}</a>
              {:else}
                {formatarData(valor)}
              {/if}
            {:else}
              <span class="mono">{typeof valor === 'string' ? valor : JSON.stringify(valor)}</span>
              {#each datasDosValores(valor) as d (d.chave)}
                {@const fato = fatoDaData(a, d.data)}
                {#if fato && linkEvidencia(fato)}
                  <a class="data-interna" href={linkEvidencia(fato)} data-testid="link-data">{formatarData(d.data)}</a>
                {/if}
              {/each}
            {/if}
          </dd>
        {/each}
      </dl>

      <h3>Fatos usados</h3>
      <ul class="fatos">
        {#each a.fatos_usados as fid (fid)}
          {@const fato = porId.get(fid)}
          {#if fato}
            <li data-testid="fato" data-fato={fato.id}>
              <span>{legivel(fato.tipo)}: <strong>{textoDoValor(fato.valor)}</strong></span>
              <span class="selo" data-testid="status-fato">{STATUS_FATO[fato.status] ?? fato.status}</span>
              {#if !fato.vigente}<span class="selo antigo">substituído</span>{/if}
              {#each fato.evidencias as ev (ev.id)}
                <a href="/processos/{id}/visualizador?evidencia={ev.id}" data-testid="link-evidencia">
                  fl. {ev.pagina ?? '?'}
                </a>
              {/each}
              {#if fato.vigente && podeAnotar}
                {#if editando === fato.id}
                  <form
                    class="correcao"
                    onsubmit={(e) => {
                      e.preventDefault();
                      void registrar(fato, 'corrigido');
                    }}
                  >
                    <label for="valor-{fato.id}">Valor corrigido</label>
                    <input id="valor-{fato.id}" bind:value={valorNovo} />
                    <button type="submit">Salvar correção</button>
                    <button type="button" class="secundario" onclick={() => (editando = null)}>Cancelar</button>
                  </form>
                {:else}
                  <button type="button" class="secundario" onclick={() => void registrar(fato, 'confirmado')}>Confirmar</button>
                  <button type="button" class="secundario" onclick={() => iniciarCorrecao(fato)}>Corrigir</button>
                {/if}
              {/if}
              {@render notas(notasDe({ fato: fato.id }))}
              {@render formNota(`f-${a.id}-${fato.id}`, { fato_id: fato.id })}
            </li>
          {:else}
            <li class="dica">Fato {fid} (não encontrado)</li>
          {/if}
        {/each}
      </ul>
      <p class="dica">Versão do catálogo {a.versao_catalogo} · {formatarData(a.criado_em)}</p>
      {@render notas(notasDe({ achado: a.id }))}
      {@render formNota(`a-${a.id}`, { achado_id: a.id })}
    </article>
  {/each}
{/if}

<h2>Histórico</h2>
{#if antigos.length === 0 && substituidos.length === 0}
  <p class="dica">Sem versões anteriores.</p>
{:else}
  {#if antigos.length}
    <h3>Achados anteriores</h3>
    <table data-testid="historico-achados">
      <thead>
        <tr><th scope="col">Validação</th><th scope="col">Resultado</th><th scope="col">Explicação</th><th scope="col">Gravado em</th></tr>
      </thead>
      <tbody>
        {#each antigos as a (a.id)}
          <tr>
            <td>{legivel(a.validacao)}</td>
            <td>{RESULTADO[a.resultado] ?? a.resultado}</td>
            <td>{a.explicacao}</td>
            <td>{formatarData(a.criado_em)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
  {#if substituidos.length}
    <h3>Fatos substituídos</h3>
    <ul data-testid="historico-fatos">
      {#each substituidos as f (f.id)}
        {@const novo = f.substituido_por ? porId.get(f.substituido_por) : undefined}
        <li>
          {legivel(f.tipo)}: {textoDoValor(f.valor)} ({STATUS_FATO[f.status] ?? f.status})
          {#if novo}→ {textoDoValor(novo.valor)} ({STATUS_FATO[novo.status] ?? novo.status}){/if}
        </li>
      {/each}
    </ul>
  {/if}
{/if}

<style>
  .achado {
    margin-bottom: 1rem;
  }
  .achado header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }
  .achado h2 {
    margin: 0;
  }
  h3 {
    font-size: 1rem;
    margin: 1rem 0 0.5rem;
  }
  .resultado {
    font-weight: 700;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    border: 1px solid currentColor;
  }
  .resultado.conforme {
    color: var(--sucesso);
    background: var(--sucesso-fundo);
  }
  .resultado.atencao {
    color: var(--perigo);
    background: var(--perigo-fundo);
  }
  .resultado.verificar {
    color: var(--aviso-texto);
    background: var(--aviso-fundo);
  }
  .valores {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 1rem;
    margin: 0;
  }
  dt {
    font-weight: 600;
  }
  dd {
    margin: 0;
  }
  .data-interna {
    margin-left: 0.5rem;
  }
  .fatos li {
    margin-bottom: 0.6rem;
  }
  .fatos a,
  .fatos button {
    margin-left: 0.4rem;
  }
  .selo {
    display: inline-block;
    padding: 0 0.4rem;
    margin-left: 0.4rem;
    border: 1px solid var(--borda);
    border-radius: 999px;
    font-size: 0.8rem;
  }
  .selo.antigo {
    color: var(--texto-suave);
  }
  .correcao,
  .nota {
    margin-top: 0.5rem;
    max-width: 30rem;
  }
  textarea {
    font: inherit;
    width: 100%;
    color: var(--texto);
    background: var(--superficie);
    border: 1px solid var(--borda);
    border-radius: var(--raio);
    padding: 0.4rem;
  }
  .notas {
    font-size: 0.9rem;
    color: var(--texto-suave);
  }
</style>
