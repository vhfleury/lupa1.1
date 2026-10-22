<script lang="ts">
  // Página como IMAGEM renderizada pelo servidor (nunca o PDF cru nem o texto extraído), com o
  // destaque da evidência desenhado por cima em coordenadas de fração da página. Navegação por
  // botões e teclado (setas/PageUp/PageDown, Home/End, + e -).
  import { BASE_API } from '$lib/api';
  import type { BboxEvidencia } from '$lib/processos/tipos';
  import { paginaDestino, retanguloDestaque, proximoZoom, ZOOM_MAX, ZOOM_MIN } from './geometria';

  interface Props {
    processoId: string;
    arquivoId: string;
    pagina: number;
    totalPaginas: number | null;
    destaque: BboxEvidencia | null;
    aoMudarPagina: (pagina: number) => void;
  }

  let { processoId, arquivoId, pagina, totalPaginas, destaque, aoMudarPagina }: Props = $props();

  let zoom = $state(1);
  let carregando = $state(true);
  let falhou = $state(false);
  let moldura = $state<HTMLDivElement | null>(null);

  const src = $derived(
    `${BASE_API}/processos/${encodeURIComponent(processoId)}/arquivos/${encodeURIComponent(arquivoId)}/paginas/${pagina}/imagem`,
  );
  const retangulos = $derived(
    destaque && destaque.arquivo_id === arquivoId && destaque.pagina === pagina
      ? destaque.retangulos
      : [],
  );

  $effect(() => {
    void src;
    carregando = true;
    falhou = false;
  });

  function ir(delta: number): void {
    const destino = paginaDestino(pagina, delta, totalPaginas);
    if (destino !== pagina) aoMudarPagina(destino);
  }

  function teclado(evento: KeyboardEvent): void {
    // Só com o foco na página: setas em campos de formulário continuam sendo dos campos.
    if (!moldura || !(evento.target instanceof Node) || !moldura.contains(evento.target)) return;
    const acoes: Record<string, () => void> = {
      ArrowRight: () => ir(1),
      PageDown: () => ir(1),
      ArrowLeft: () => ir(-1),
      PageUp: () => ir(-1),
      Home: () => aoMudarPagina(1),
      End: () => totalPaginas !== null && aoMudarPagina(totalPaginas),
      '+': () => (zoom = proximoZoom(zoom, 1)),
      '=': () => (zoom = proximoZoom(zoom, 1)),
      '-': () => (zoom = proximoZoom(zoom, -1)),
    };
    const acao = acoes[evento.key];
    if (acao) {
      evento.preventDefault();
      acao();
    }
  }
</script>

<div class="barra" role="toolbar" aria-label="Navegação da página">
  <button type="button" class="secundario" onclick={() => ir(-1)} disabled={pagina <= 1}>
    ← Anterior
  </button>
  <span data-testid="pagina-atual" aria-live="polite">
    Página {pagina}{totalPaginas !== null ? ` de ${totalPaginas}` : ''}
  </span>
  <button
    type="button"
    class="secundario"
    onclick={() => ir(1)}
    disabled={totalPaginas !== null && pagina >= totalPaginas}
  >
    Próxima →
  </button>
  <span class="separador"></span>
  <button
    type="button"
    class="secundario"
    aria-label="Diminuir zoom"
    onclick={() => (zoom = proximoZoom(zoom, -1))}
    disabled={zoom <= ZOOM_MIN}>−</button
  >
  <span data-testid="zoom">{Math.round(zoom * 100)}%</span>
  <button
    type="button"
    class="secundario"
    aria-label="Aumentar zoom"
    onclick={() => (zoom = proximoZoom(zoom, 1))}
    disabled={zoom >= ZOOM_MAX}>+</button
  >
</div>

<svelte:window onkeydown={teclado} />

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  class="moldura"
  tabindex="0"
  role="region"
  aria-label="Página {pagina} (use as setas para navegar e + ou − para o zoom)"
  bind:this={moldura}
  data-testid="moldura-pagina"
>
  <!-- 6.10: `style:` usa a API CSSOM (permitida pela CSP); atributo style inline seria bloqueado. -->
  <div class="folha" style:width="{zoom * 100}%">
    <img
      {src}
      alt="Página {pagina} do arquivo, renderizada pelo servidor"
      onload={() => (carregando = false)}
      onerror={() => {
        carregando = false;
        falhou = true;
      }}
      draggable="false"
      data-testid="imagem-pagina"
    />
    {#each retangulos as r, i (i)}
      {@const pos = retanguloDestaque(r)}
      <div
        class="destaque"
        style:left={pos.left}
        style:top={pos.top}
        style:width={pos.width}
        style:height={pos.height}
        data-testid="destaque-evidencia"
      ></div>
    {/each}
  </div>
  {#if carregando}<p class="estado">Carregando a página…</p>{/if}
  {#if falhou}<p class="estado erro" role="alert">Não foi possível mostrar esta página.</p>{/if}
</div>

<style>
  .barra {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  .separador {
    flex: 1;
  }
  .moldura {
    position: relative;
    overflow: auto;
    max-height: 80vh;
    border: 1px solid var(--borda);
    background: #8a8f98;
    padding: 1rem;
  }
  .folha {
    position: relative;
    margin: 0 auto;
    min-width: 10rem;
    box-shadow: 0 1px 6px rgb(0 0 0 / 35%);
  }
  img {
    display: block;
    width: 100%;
    height: auto;
    background: #fff;
    user-select: none;
  }
  .destaque {
    position: absolute;
    background: rgb(255 214 0 / 35%);
    outline: 2px solid #c77c00;
    pointer-events: none;
  }
  .estado {
    position: absolute;
    top: 1rem;
    left: 1rem;
    margin: 0;
    background: var(--superficie);
    padding: 0.25rem 0.5rem;
    border-radius: var(--raio);
  }
  .erro {
    color: var(--perigo);
  }
</style>
