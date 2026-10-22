<script lang="ts">
  // Processos do gabinete: lista com o status da ingestão (polling leve enquanto algo
  // processa) e criação de processo com o número CNJ validado aqui e no servidor.
  import { onDestroy, onMount } from 'svelte';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import { mascararCnj, problemaCnj } from '$lib/processos/cnj';
  import { formatarData, legivel, SITUACAO } from '$lib/processos/rotulos';
  import type { Materia, Processo, ProcessoNaLista } from '$lib/processos/tipos';
  import { sessao, tem } from '$lib/sessao.svelte';

  const INTERVALO_MS = 4000;

  let processos = $state<ProcessoNaLista[]>([]);
  let carregando = $state(true);
  let erro = $state('');
  let aviso = $state('');
  let numero = $state('');
  let classe = $state('');
  let materia = $state<Materia>('criminal');
  let sigiloso = $state(false);
  let tocado = $state(false);
  let enviando = $state(false);
  let temporizador: ReturnType<typeof setTimeout> | undefined;

  const atual = $derived(sessao.atual);
  const podeCriar = $derived(tem(atual, 'subir_processo') && atual?.gabinete_id !== null);
  const problema = $derived(problemaCnj(numero));
  const processando = $derived(processos.some((p) => p.ingestao.situacao === 'processando'));

  async function carregar(): Promise<void> {
    try {
      processos = await chamar<ProcessoNaLista[]>('GET', '/processos');
      erro = '';
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      carregando = false;
      agendar();
    }
  }

  function agendar(): void {
    clearTimeout(temporizador);
    if (processando) temporizador = setTimeout(() => void carregar(), INTERVALO_MS);
  }

  onMount(() => void carregar());
  onDestroy(() => clearTimeout(temporizador));

  async function criar(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    tocado = true;
    aviso = '';
    if (problema || classe.trim().length < 2) return;
    enviando = true;
    try {
      const criado = await chamar<Processo>('POST', '/processos', {
        numero_cnj: numero.trim(),
        classe: classe.trim(),
        materia,
        sigiloso,
      });
      aviso = `Processo ${criado.numero_cnj} criado.`;
      numero = '';
      classe = '';
      sigiloso = false;
      tocado = false;
      await carregar();
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      enviando = false;
    }
  }
</script>

<svelte:head><title>Processos · Lupa</title></svelte:head>

<h1>Processos</h1>

{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
{#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

{#if podeCriar}
  <section class="cartao" aria-labelledby="titulo-novo">
    <h2 id="titulo-novo">Novo processo</h2>
    <form onsubmit={criar} novalidate>
      <div class="grade">
        <div class="campo">
          <label for="cnj">Número CNJ</label>
          <input
            id="cnj"
            inputmode="numeric"
            autocomplete="off"
            placeholder="0000000-00.0000.0.00.0000"
            value={numero}
            oninput={(e) => (numero = mascararCnj(e.currentTarget.value))}
            onblur={() => (tocado = true)}
            aria-invalid={tocado && problema !== ''}
            aria-describedby="cnj-erro"
          />
          {#if tocado && problema}<p id="cnj-erro" class="erro-campo">{problema}</p>{/if}
        </div>
        <div class="campo">
          <label for="classe">Classe</label>
          <input id="classe" bind:value={classe} placeholder="Apelação Criminal" maxlength="120" />
        </div>
        <div class="campo">
          <label for="materia">Matéria</label>
          <select id="materia" bind:value={materia}>
            <option value="criminal">Criminal</option>
            <option value="civel">Cível</option>
          </select>
        </div>
      </div>
      <div class="campo linha">
        <input id="sigiloso" type="checkbox" bind:checked={sigiloso} />
        <label for="sigiloso">Processo sigiloso (a ingestão fica bloqueada na v1)</label>
      </div>
      <button type="submit" disabled={enviando}>Criar processo</button>
    </form>
  </section>
{/if}

<h2>Processos do gabinete</h2>
{#if carregando}
  <p role="status">Carregando…</p>
{:else if processos.length === 0}
  <p class="dica">Nenhum processo cadastrado.</p>
{:else}
  <table data-testid="lista-processos">
    <thead>
      <tr>
        <th scope="col">Número CNJ</th>
        <th scope="col">Classe</th>
        <th scope="col">Matéria</th>
        <th scope="col">Processamento</th>
        <th scope="col">Criado em</th>
      </tr>
    </thead>
    <tbody>
      {#each processos as p (p.id)}
        <tr data-processo={p.id}>
          <td><a class="mono" href="/processos/{p.id}">{p.numero_cnj}</a></td>
          <td>{p.classe}</td>
          <td>{legivel(p.materia)}</td>
          <td>
            <span class="selo {p.ingestao.situacao}" data-testid="situacao">
              {SITUACAO[p.ingestao.situacao] ?? p.ingestao.situacao}
            </span>
            {#if p.sigiloso}<span class="selo sigiloso">Sigiloso</span>{/if}
          </td>
          <td>{formatarData(p.criado_em)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if processando}<p class="dica" aria-live="polite">Atualizando o status automaticamente…</p>{/if}
{/if}

<style>
  .grade {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    gap: 0 1rem;
  }
  .linha {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .linha input {
    width: auto;
  }
  .linha label {
    margin: 0;
    font-weight: 400;
  }
  .erro-campo {
    color: var(--perigo);
    margin: 0.25rem 0 0;
    font-size: 0.9rem;
  }
  .selo {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    border: 1px solid var(--borda);
    font-size: 0.85rem;
  }
  .selo.concluido {
    background: var(--sucesso-fundo);
    color: var(--sucesso);
  }
  .selo.quarentena,
  .selo.falho {
    background: var(--perigo-fundo);
    color: var(--perigo);
  }
  .selo.processando,
  .selo.pendencias,
  .selo.sigiloso {
    background: var(--aviso-fundo);
    color: var(--aviso-texto);
  }
</style>
