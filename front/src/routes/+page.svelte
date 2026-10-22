<script lang="ts">
  import { sessao } from '$lib/sessao.svelte';
  import { ROTULO_PAPEL } from '$lib/tipos';

  const atual = $derived(sessao.atual);
</script>

<svelte:head><title>Início · Lupa</title></svelte:head>

{#if atual}
  <h1>Olá, {atual.nome_usuario}</h1>
  <section class="cartao" aria-labelledby="titulo-sessao">
    <h2 id="titulo-sessao">Sessão</h2>
    <dl data-testid="estado-sessao">
      <dt>Usuário</dt>
      <dd>{atual.nome_usuario}</dd>
      <dt>Papel</dt>
      <dd>{ROTULO_PAPEL[atual.papel]}</dd>
      <dt>Gabinete</dt>
      <dd class="mono">{atual.gabinete_id ?? 'todos (administração)'}</dd>
      <dt>Situação</dt>
      <dd>Sessão ativa</dd>
    </dl>
    <p class="dica">A sessão termina depois de 30 minutos sem uso ou 8 horas depois do login.</p>
  </section>
{/if}

<style>
  dl {
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
</style>
