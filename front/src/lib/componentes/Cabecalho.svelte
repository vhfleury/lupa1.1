<script lang="ts">
  import SeletorTema from '$lib/componentes/SeletorTema.svelte';
  import { ROTULO_PAPEL, type Sessao } from '$lib/tipos';

  interface Props {
    sessao: Sessao;
    aoSair: () => void;
  }

  let { sessao, aoSair }: Props = $props();
</script>

<header class="cabecalho">
  <a class="marca" href="/">Lupa</a>
  <div class="usuario">
    <SeletorTema id="tema-cabecalho" />
    <span data-testid="usuario-nome">{sessao.nome_usuario}</span>
    <span class="papel" data-testid="usuario-papel">{ROTULO_PAPEL[sessao.papel]}</span>
    <button type="button" class="secundario" onclick={aoSair}>Sair</button>
  </div>
</header>

<style>
  .cabecalho {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.6rem 1.25rem;
    background: var(--superficie);
    border-bottom: 1px solid var(--borda);
  }
  .marca {
    font-weight: 700;
    font-size: 1.2rem;
    text-decoration: none;
  }
  .usuario {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  .papel {
    color: var(--texto-suave);
    border: 1px solid var(--borda);
    border-radius: 999px;
    padding: 0 0.6rem;
    font-size: 0.9rem;
  }
</style>
