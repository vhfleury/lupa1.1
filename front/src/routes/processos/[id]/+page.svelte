<script lang="ts">
  // Página do processo: dados, envio de PDF/ZIP com barra de progresso (stream, sem travar a
  // interface) e acompanhamento dos arquivos por polling leve enquanto a fila trabalha.
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/state';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import {
    enviarArquivo,
    formatarBytes,
    problemaArquivo,
    type EnvioEmCurso,
    type Progresso,
  } from '$lib/processos/envio';
  import {
    ESTADO_JOB,
    ESTADOS_FINAIS,
    formatarData,
    legivel,
    motivoFalha,
    motivoQuarentena,
    SITUACAO,
  } from '$lib/processos/rotulos';
  import type { ArquivosDoProcesso, Processo } from '$lib/processos/tipos';
  import { sessao, tem } from '$lib/sessao.svelte';

  const INTERVALO_MS = 2500;

  const id = $derived(page.params['id'] ?? '');
  let processo = $state<Processo | null>(null);
  let dados = $state<ArquivosDoProcesso | null>(null);
  let erro = $state('');
  let aviso = $state('');
  let progresso = $state<Progresso | null>(null);
  let envio: EnvioEmCurso | null = null;
  let seletor = $state<HTMLInputElement | null>(null);
  let temporizador: ReturnType<typeof setTimeout> | undefined;
  let ativo = true;

  const podeEnviar = $derived(tem(sessao.atual, 'subir_processo') && processo?.sigiloso === false);
  const pendente = $derived(
    dados?.arquivos.some((a) => a.estado !== null && !ESTADOS_FINAIS.has(a.estado)) ?? false,
  );
  const pronto = $derived(dados?.arquivos.some((a) => a.estado === 'concluido' || a.estado === 'em_revisao') ?? false);
  const percentual = $derived(
    progresso && progresso.total > 0 ? Math.floor((progresso.enviados / progresso.total) * 100) : 0,
  );

  async function carregarArquivos(): Promise<void> {
    try {
      dados = await chamar<ArquivosDoProcesso>('GET', `/processos/${id}/arquivos`);
    } catch (e) {
      erro = mensagemErro(e);
    }
    clearTimeout(temporizador);
    if (ativo && pendente) temporizador = setTimeout(() => void carregarArquivos(), INTERVALO_MS);
  }

  onMount(async () => {
    try {
      processo = await chamar<Processo>('GET', `/processos/${id}`);
      await carregarArquivos();
    } catch (e) {
      erro = mensagemErro(e);
    }
  });

  onDestroy(() => {
    ativo = false;
    clearTimeout(temporizador);
    envio?.cancelar();
  });

  async function enviar(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    erro = '';
    aviso = '';
    const arquivo = seletor?.files?.[0];
    if (!arquivo) {
      erro = 'Escolha um arquivo PDF ou ZIP.';
      return;
    }
    const problema = problemaArquivo(arquivo);
    if (problema) {
      erro = problema;
      return;
    }
    progresso = { enviados: 0, total: arquivo.size };
    envio = enviarArquivo(id, arquivo, (p) => (progresso = p));
    try {
      const resposta = await envio.promessa;
      aviso = resposta.duplicado
        ? `${arquivo.name}: este conteúdo já tinha sido enviado neste processo.`
        : `${arquivo.name} recebido (${formatarBytes(resposta.tamanho_bytes)}). Processando…`;
      if (seletor) seletor.value = '';
      await carregarArquivos();
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      envio = null;
      progresso = null;
    }
  }
</script>

<svelte:head><title>{processo?.numero_cnj ?? 'Processo'} · Lupa</title></svelte:head>

<p><a href="/processos">← Processos</a></p>
{#if processo}
  <h1 class="mono">{processo.numero_cnj}</h1>
  <p>
    {processo.classe} · {legivel(processo.materia)} · status {legivel(processo.status)}
    {#if processo.sigiloso}· <strong>sigiloso (ingestão bloqueada na v1)</strong>{/if}
  </p>
  <nav class="atalhos" aria-label="Telas do processo">
    <a href="/processos/{id}/dossie">Dossiê e linha do tempo</a>
    <a href="/processos/{id}/validacoes">Validações</a>
    <a href="/processos/{id}/visualizador">Visualizador</a>
  </nav>
{/if}

{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
{#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

{#if podeEnviar}
  <section class="cartao" aria-labelledby="titulo-envio">
    <h2 id="titulo-envio">Enviar autos</h2>
    <form onsubmit={enviar}>
      <div class="campo">
        <label for="arquivo">Arquivo PDF ou ZIP (até 512 MB)</label>
        <input id="arquivo" type="file" accept=".pdf,.zip,application/pdf,application/zip" bind:this={seletor} disabled={progresso !== null} />
      </div>
      {#if progresso}
        <div class="progresso" data-testid="progresso-envio">
          <label for="barra">Enviando… {percentual}%</label>
          <progress id="barra" max="100" value={percentual}>{percentual}%</progress>
          <span class="dica">{formatarBytes(progresso.enviados)} de {formatarBytes(progresso.total)}</span>
          <!-- 6.10: anúncio de progresso para leitor de tela, em degraus de 10% (não a cada byte). -->
          <span class="visualmente-oculto" aria-live="polite" data-testid="anuncio-envio"
            >Enviando: {Math.floor(percentual / 10) * 10}%</span
          >
          <button type="button" class="secundario" onclick={() => envio?.cancelar()}>Cancelar</button>
        </div>
      {:else}
        <button type="submit">Enviar</button>
      {/if}
    </form>
  </section>
{/if}

<h2>Arquivos</h2>
{#if dados}
  <p>
    Situação: <strong data-testid="situacao-processo">{SITUACAO[dados.situacao] ?? dados.situacao}</strong>
    {#if pendente}<span class="dica" aria-live="polite"> — atualizando automaticamente…</span>{/if}
  </p>
  {#if dados.arquivos.length === 0}
    <p class="dica">Nenhum arquivo enviado.</p>
  {:else}
    <table data-testid="lista-arquivos">
      <thead>
        <tr>
          <th scope="col">Arquivo</th>
          <th scope="col">Tamanho</th>
          <th scope="col">Enviado em</th>
          <th scope="col">Estado</th>
          <th scope="col">Páginas</th>
        </tr>
      </thead>
      <tbody>
        {#each dados.arquivos as a (a.arquivo_id)}
          <tr data-arquivo={a.arquivo_id}>
            <td>{a.nome}</td>
            <td>{formatarBytes(a.tamanho_bytes)}</td>
            <td>{formatarData(a.enviado_em)}</td>
            <td>
              <span data-testid="estado-arquivo" data-estado={a.estado}>{a.estado ? (ESTADO_JOB[a.estado] ?? a.estado) : '—'}</span>
              {#if a.estado === 'quarentena'}
                <p class="motivo" data-testid="motivo-quarentena">{motivoQuarentena(a.motivo_quarentena)}</p>
              {:else if a.estado === 'falho'}
                <p class="motivo">{motivoFalha(a.motivo_falha)}</p>
              {/if}
            </td>
            <td>
              {#if a.total_paginas && (a.estado === 'concluido' || a.estado === 'em_revisao')}
                <a href="/processos/{id}/visualizador?arquivo={a.arquivo_id}&pagina=1">{a.total_paginas}</a>
              {:else}
                {a.total_paginas ?? '—'}
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if pronto}
      <p><a href="/processos/{id}/dossie">Abrir o dossiê</a></p>
    {/if}
  {/if}
{/if}

<style>
  .atalhos {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  .progresso {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem;
  }
  .progresso label {
    margin: 0;
  }
  progress {
    flex: 1;
    min-width: 12rem;
    height: 1.1rem;
  }
  .motivo {
    margin: 0.25rem 0 0;
    color: var(--perigo);
    font-size: 0.9rem;
  }
</style>
