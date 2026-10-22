<script lang="ts">
  // Tela do administrador: gabinetes e desembargadores.
  import { onMount } from 'svelte';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import FormNovoUsuario from '$lib/componentes/FormNovoUsuario.svelte';
  import SenhaTemporaria from '$lib/componentes/SenhaTemporaria.svelte';
  import { sessao, tem } from '$lib/sessao.svelte';
  import type { Gabinete, UsuarioComSenha } from '$lib/tipos';

  let gabinetes = $state<Gabinete[]>([]);
  let nome = $state('');
  let erro = $state('');
  let aviso = $state('');
  let carregando = $state(true);
  let senhaMostrada = $state<{ nome: string; senha: string } | null>(null);

  const permitido = $derived(tem(sessao.atual, 'gerir_gabinetes'));

  async function carregar(): Promise<void> {
    try {
      gabinetes = await chamar<Gabinete[]>('GET', '/gabinetes');
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      carregando = false;
    }
  }

  onMount(() => {
    if (permitido) void carregar();
    else carregando = false;
  });

  async function criarGabinete(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    erro = '';
    aviso = '';
    try {
      const criado = await chamar<Gabinete>('POST', '/gabinetes', { nome: nome.trim() });
      aviso = `Gabinete ${criado.nome} criado.`;
      nome = '';
      await carregar();
    } catch (e) {
      erro = mensagemErro(e);
    }
  }

  function aoCriar(criado: UsuarioComSenha): void {
    erro = '';
    aviso = `Desembargador ${criado.nome_usuario} criado.`;
    senhaMostrada = { nome: criado.nome_usuario, senha: criado.senha_temporaria };
  }
</script>

<svelte:head><title>Gabinetes · Lupa</title></svelte:head>

<h1>Gabinetes</h1>

{#if !permitido}
  <Aviso tipo="erro">Só o administrador gerencia gabinetes.</Aviso>
{:else}
  {#if senhaMostrada}
    <SenhaTemporaria
      nomeUsuario={senhaMostrada.nome}
      senha={senhaMostrada.senha}
      aoFechar={() => (senhaMostrada = null)}
    />
  {/if}
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
  {#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

  {#if carregando}
    <p role="status">Carregando…</p>
  {:else}
    <ul class="lista" aria-label="Gabinetes cadastrados">
      {#each gabinetes as gabinete (gabinete.id)}
        <li>{gabinete.nome}</li>
      {:else}
        <li>Nenhum gabinete cadastrado.</li>
      {/each}
    </ul>
  {/if}

  <div class="grade">
    <form class="cartao" onsubmit={criarGabinete} aria-labelledby="titulo-novo-gabinete">
      <h2 id="titulo-novo-gabinete">Novo gabinete</h2>
      <div class="campo">
        <label for="nome-gabinete">Nome do gabinete</label>
        <input id="nome-gabinete" bind:value={nome} required maxlength="200" />
      </div>
      <button type="submit">Criar gabinete</button>
    </form>

    {#if gabinetes.length > 0}
      <FormNovoUsuario papeis={['desembargador']} {gabinetes} titulo="Novo desembargador" {aoCriar} />
    {/if}
  </div>
{/if}

<style>
  .lista {
    background: var(--superficie);
    border: 1px solid var(--borda);
    border-radius: var(--raio);
    padding: 0.75rem 2rem;
  }
  .grade {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
    gap: 1.25rem;
    margin-top: 1.5rem;
  }
</style>
