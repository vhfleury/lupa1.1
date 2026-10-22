<script lang="ts">
  // Dossiê do processo: ficha (réus só por pseudônimo), índice de peças, linha do tempo
  // clicável (abre o visualizador na página da evidência), alertas de saneamento e achados.
  // Todo campo produzido por modelo vem rotulado `gerado` e aparece destacado como tal.
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import { formatarData, legivel, RESULTADO } from '$lib/processos/rotulos';
  import type { Dossie, Fato, Indice } from '$lib/processos/tipos';

  const id = $derived(page.params['id'] ?? '');
  let dossie = $state<Dossie | null>(null);
  let indice = $state<Indice | null>(null);
  let fatos = $state<Fato[]>([]);
  let erro = $state('');
  let gerando = $state(false);

  const paginaParaArquivo = $derived(
    new Map(
      fatos.flatMap((f) =>
        f.evidencias.map((e) => [e.pagina_id, { arquivo: e.arquivo_id, pagina: e.pagina }] as const),
      ),
    ),
  );

  async function carregar(resumos = false): Promise<void> {
    try {
      const [d, i, f] = await Promise.all([
        chamar<Dossie>('GET', `/processos/${id}/dossie${resumos ? '?resumos=true' : ''}`),
        chamar<Indice>('GET', `/processos/${id}/indice`),
        chamar<{ fatos: Fato[] }>('GET', `/processos/${id}/fatos`),
      ]);
      dossie = d;
      indice = i;
      fatos = f.fatos;
    } catch (e) {
      erro = mensagemErro(e);
    }
  }

  onMount(() => void carregar());

  async function gerarResumos(): Promise<void> {
    gerando = true;
    await carregar(true);
    gerando = false;
  }

  function linkEvento(fatoId: string, paginaId: string): string {
    const fato = fatos.find((f) => f.id === fatoId);
    const evidencia = fato?.evidencias.find((e) => e.pagina_id === paginaId) ?? fato?.evidencias[0];
    if (evidencia) return `/processos/${id}/visualizador?evidencia=${evidencia.id}`;
    const local = paginaParaArquivo.get(paginaId);
    return local?.arquivo
      ? `/processos/${id}/visualizador?arquivo=${local.arquivo}&pagina=${local.pagina ?? 1}`
      : `/processos/${id}/visualizador`;
  }

  function linkPagina(arquivoId: string, pagina: number): string {
    return `/processos/${id}/visualizador?arquivo=${arquivoId}&pagina=${pagina}`;
  }

  function percentual(valor: number): string {
    return `${Math.round(valor * 100)}%`;
  }
</script>

<svelte:head><title>Dossiê · Lupa</title></svelte:head>

<p><a href="/processos/{id}">← Processo</a></p>
<h1>Dossiê</h1>
{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}

{#if dossie}
  <section class="cartao" aria-labelledby="t-ficha">
    <h2 id="t-ficha">Ficha</h2>
    <dl class="ficha" data-testid="ficha">
      <dt>Número</dt>
      <dd class="mono">{dossie.ficha.numero_cnj}</dd>
      <dt>Classe</dt>
      <dd>{dossie.ficha.classe}</dd>
      <dt>Matéria</dt>
      <dd>{legivel(dossie.ficha.materia)}</dd>
      <dt>Status</dt>
      <dd>{legivel(dossie.ficha.status)}</dd>
      <dt>Réus</dt>
      <dd data-testid="reus">
        {dossie.ficha.reus.length ? dossie.ficha.reus.join(', ') : '—'}
        <span class="dica">(pseudônimos)</span>
      </dd>
    </dl>
  </section>

  <h2>Linha do tempo</h2>
  {#if dossie.linha_do_tempo.length === 0}
    <p class="dica">Nenhum evento extraído.</p>
  {:else}
    <ol class="linha-tempo" data-testid="linha-do-tempo">
      {#each dossie.linha_do_tempo as ev, i (`${ev.fato_id}-${i}`)}
        <li>
          <a href={linkEvento(ev.fato_id, ev.pagina_id)} data-testid="evento" data-pagina={ev.pagina}>
            <strong>{formatarData(ev.data)}</strong> — {legivel(ev.tipo)}
            {#if ev.pagina !== null}<span class="dica">(fl. {ev.pagina})</span>{/if}
          </a>
          {#if ev.status !== 'automatico'}<span class="selo">{legivel(ev.status)}</span>{/if}
          <q>{ev.trecho}</q>
        </li>
      {/each}
    </ol>
  {/if}

  <h2>Índice de peças</h2>
  {#if indice && indice.pecas.length}
    <table data-testid="indice-pecas">
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Tipo</th>
          <th scope="col">Origem</th>
          <th scope="col">Páginas</th>
          <th scope="col">Data</th>
          <th scope="col">Confiança</th>
          <th scope="col">Flags</th>
        </tr>
      </thead>
      <tbody>
        {#each indice.pecas as p (p.id)}
          {@const resumo = dossie.pecas.find((d) => d.peca_id === p.id)?.resumo_peca}
          <tr>
            <td>{p.ordem}</td>
            <td>
              {legivel(p.tipo)}
              {#if resumo}
                <div class="gerado" data-testid="gerado">
                  <span class="rotulo-gerado">gerado</span>
                  {resumo.texto}
                </div>
              {/if}
            </td>
            <td>{legivel(p.origem)}</td>
            <td>
              <a href={linkPagina(p.arquivo_id, p.pagina_inicial)}>
                {p.pagina_inicial}{p.pagina_final !== p.pagina_inicial ? `–${p.pagina_final}` : ''}
              </a>
            </td>
            <td>{formatarData(p.data)}</td>
            <td>{percentual(p.confianca)} <span class="dica">({legivel(p.metodo)})</span></td>
            <td>
              {#each p.resumo_flags.peca as flag (flag)}<span class="selo">{legivel(flag)}</span>{/each}
              {#if p.resumo_flags.total_saneamento}
                <span class="selo alerta">{p.resumo_flags.total_saneamento} alerta(s) de saneamento</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p>
      <button type="button" class="secundario" onclick={gerarResumos} disabled={gerando}>
        {gerando ? 'Gerando…' : 'Gerar resumos das peças (modelo)'}
      </button>
      <span class="dica">Texto gerado pelo modelo aparece marcado como <span class="rotulo-gerado">gerado</span>.</span>
    </p>
  {:else}
    <p class="dica">Índice ainda não disponível.</p>
  {/if}

  <h2>Alertas de saneamento</h2>
  {#if dossie.alertas.length === 0}
    <p class="dica">Nenhuma página sinalizada.</p>
  {:else}
    <ul data-testid="alertas">
      {#each dossie.alertas as alerta, i (`${alerta.pagina_id}-${i}`)}
        <li>
          <a href={linkPagina(alerta.arquivo_id, alerta.pagina)}>Página {alerta.pagina}</a>:
          {alerta.flags.map(legivel).join(', ')}
        </li>
      {/each}
    </ul>
  {/if}

  <h2>Achados</h2>
  {#if dossie.achados.length === 0}
    <p class="dica">Nenhum achado.</p>
  {:else}
    <ul>
      {#each dossie.achados as a (a.achado_id)}
        <li>
          <strong>{legivel(a.validacao)}</strong>: {RESULTADO[a.resultado] ?? a.resultado} — {a.explicacao}
        </li>
      {/each}
    </ul>
    <p><a href="/processos/{id}/validacoes">Ver validações completas</a></p>
  {/if}
{:else if !erro}
  <p role="status">Carregando…</p>
{/if}

<style>
  .ficha {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.35rem 1rem;
    margin: 0;
  }
  dt {
    font-weight: 600;
  }
  dd {
    margin: 0;
  }
  .linha-tempo {
    border-left: 3px solid var(--borda);
    padding-left: 1.25rem;
  }
  .linha-tempo li {
    margin-bottom: 0.75rem;
  }
  .linha-tempo q {
    display: block;
    color: var(--texto-suave);
    font-size: 0.9rem;
  }
  .selo {
    display: inline-block;
    padding: 0 0.4rem;
    margin: 0 0.25rem 0.25rem 0;
    border: 1px solid var(--borda);
    border-radius: 999px;
    font-size: 0.8rem;
  }
  .selo.alerta {
    background: var(--aviso-fundo);
    color: var(--aviso-texto);
  }
  .gerado {
    margin-top: 0.35rem;
    padding: 0.35rem 0.5rem;
    border-left: 4px dashed var(--foco);
    background: var(--aviso-fundo);
    color: var(--aviso-texto);
    font-size: 0.9rem;
  }
  .rotulo-gerado {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    border: 1px solid currentColor;
    border-radius: var(--raio);
    padding: 0 0.3rem;
    margin-right: 0.35rem;
  }
</style>
