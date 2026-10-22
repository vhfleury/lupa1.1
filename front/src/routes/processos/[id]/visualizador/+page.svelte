<script lang="ts">
  // Visualizador: ?arquivo=&pagina=&evidencia=. Com `evidencia`, o servidor calcula o
  // retângulo do trecho (GET /evidencias/{id}/bbox) e a tela abre na página dele.
  import { onMount } from 'svelte';
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import type { ArquivosDoProcesso, BboxEvidencia } from '$lib/processos/tipos';
  import Visualizador from '$lib/visualizador/Visualizador.svelte';

  const id = $derived(page.params['id'] ?? '');
  let arquivos = $state<ArquivosDoProcesso | null>(null);
  let arquivoId = $state('');
  let pagina = $state(1);
  let destaque = $state<BboxEvidencia | null>(null);
  let erro = $state('');
  let semDestaque = $state(false);

  const arquivo = $derived(arquivos?.arquivos.find((a) => a.arquivo_id === arquivoId) ?? null);
  const legiveis = $derived(
    arquivos?.arquivos.filter((a) => a.total_paginas && (a.estado === 'concluido' || a.estado === 'em_revisao')) ?? [],
  );

  function sincronizarUrl(): void {
    const url = new URL(page.url);
    url.searchParams.set('arquivo', arquivoId);
    url.searchParams.set('pagina', String(pagina));
    replaceState(url, {});
  }

  function mudarPagina(nova: number): void {
    pagina = nova;
    sincronizarUrl();
  }

  onMount(async () => {
    const consulta = page.url.searchParams;
    try {
      arquivos = await chamar<ArquivosDoProcesso>('GET', `/processos/${id}/arquivos`);
      const evidencia = consulta.get('evidencia');
      if (evidencia) {
        destaque = await chamar<BboxEvidencia>('GET', `/processos/${id}/evidencias/${evidencia}/bbox`);
        arquivoId = destaque.arquivo_id;
        pagina = destaque.pagina;
        semDestaque = destaque.uniao === null;
      } else {
        arquivoId = consulta.get('arquivo') ?? legiveis[0]?.arquivo_id ?? '';
        pagina = Math.max(1, Number.parseInt(consulta.get('pagina') ?? '1', 10) || 1);
      }
    } catch (e) {
      erro = mensagemErro(e);
    }
  });
</script>

<svelte:head><title>Visualizador · Lupa</title></svelte:head>

<p><a href="/processos/{id}">← Processo</a></p>
<h1>Visualizador</h1>

{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}

{#if legiveis.length > 1}
  <div class="campo seletor">
    <label for="arquivo">Arquivo</label>
    <select
      id="arquivo"
      value={arquivoId}
      onchange={(e) => {
        arquivoId = e.currentTarget.value;
        mudarPagina(1);
      }}
    >
      {#each legiveis as a (a.arquivo_id)}
        <option value={a.arquivo_id}>{a.nome}</option>
      {/each}
    </select>
  </div>
{/if}

{#if destaque}
  <section class="cartao evidencia" aria-label="Evidência destacada">
    <strong>Trecho da evidência</strong> (página {destaque.pagina}):
    <q data-testid="trecho-evidencia">{destaque.trecho}</q>
    {#if semDestaque}
      <p class="dica">Esta página não tem coordenadas de texto; o trecho não pôde ser destacado.</p>
    {/if}
  </section>
{/if}

{#if arquivoId}
  <Visualizador
    processoId={id}
    {arquivoId}
    {pagina}
    totalPaginas={arquivo?.total_paginas ?? null}
    {destaque}
    aoMudarPagina={mudarPagina}
  />
  <p class="dica">
    A página é uma imagem desenhada pelo servidor a partir do original, sem camadas opcionais e
    recortada à área visível. O texto extraído não é exibido aqui.
  </p>
{:else if arquivos}
  <p class="dica">Nenhum arquivo processado para visualizar.</p>
{/if}

<style>
  .seletor {
    max-width: 24rem;
  }
  .evidencia {
    margin-bottom: 1rem;
  }
  q {
    font-style: italic;
  }
</style>
