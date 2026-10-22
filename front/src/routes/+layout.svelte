<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { chamar, configurarManipuladores } from '$lib/api';
  import Cabecalho from '$lib/componentes/Cabecalho.svelte';
  import MenuLateral from '$lib/componentes/MenuLateral.svelte';
  import SeletorTema from '$lib/componentes/SeletorTema.svelte';
  import { consumirMarcador } from '$lib/marcador';
  import { sessao } from '$lib/sessao.svelte';

  let { children }: { children: Snippet } = $props();

  configurarManipuladores({
    sessaoExpirada: () => {
      consumirMarcador();
      sessao.definir(null);
      void goto('/login?motivo=expirada');
    },
    trocaObrigatoria: () => {
      void goto('/trocar-senha');
    },
  });

  const atual = $derived(sessao.atual);
  const comMoldura = $derived(
    atual !== null && !atual.troca_senha_obrigatoria && page.url.pathname !== '/login',
  );

  async function sair(): Promise<void> {
    try {
      await chamar('POST', '/auth/logout', undefined, { tratarSessao: false });
    } catch {
      // Sessão já inválida: basta voltar ao login.
    }
    consumirMarcador(); // saída voluntária: o próximo login não fala em expiração
    sessao.definir(null);
    await goto('/login');
  }
</script>

<!-- 6.10: o roteador do SvelteKit trata o "#conteudo" sem mover o foco; movemos à mão. -->
<a
  class="pular"
  href="#conteudo"
  onclick={(evento) => {
    evento.preventDefault();
    document.getElementById('conteudo')?.focus();
  }}>Pular para o conteúdo</a
>
{#if comMoldura && atual}
  <Cabecalho sessao={atual} aoSair={sair} />
  <div class="corpo">
    <MenuLateral sessao={atual} caminho={page.url.pathname} />
    <main id="conteudo" tabindex="-1">
      {@render children()}
    </main>
  </div>
{:else}
  <main id="conteudo" class="avulso" tabindex="-1">
    {@render children()}
    <footer class="rodape"><SeletorTema id="tema-avulso" /></footer>
  </main>
{/if}

<style>
  .pular {
    position: absolute;
    left: -999px;
    top: 0;
    background: var(--superficie);
    padding: 0.5rem 1rem;
    z-index: 10;
  }
  .pular:focus {
    left: 0.5rem;
    top: 0.5rem;
  }
  .corpo {
    display: flex;
    min-height: calc(100vh - 3.5rem);
  }
  main {
    flex: 1;
    padding: 1.5rem;
    max-width: 72rem;
  }
  .rodape {
    margin-top: 2rem;
    display: flex;
    justify-content: flex-end;
  }
  .avulso {
    max-width: 30rem;
    margin: 3rem auto;
  }
  @media (max-width: 40rem) {
    .corpo {
      flex-direction: column;
    }
  }
</style>
