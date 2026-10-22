<script lang="ts">
  import { gereUsuarios } from '$lib/permissoes';
  import type { Sessao } from '$lib/tipos';

  interface Props {
    sessao: Sessao;
    caminho: string;
  }

  let { sessao, caminho }: Props = $props();

  const itens = $derived(
    [
      { href: '/', rotulo: 'Início', visivel: true },
      {
        href: '/processos',
        rotulo: 'Processos',
        visivel: sessao.permissoes.includes('ver_processo'),
      },
      { href: '/usuarios', rotulo: 'Usuários', visivel: gereUsuarios(sessao) },
      {
        href: '/gabinetes',
        rotulo: 'Gabinetes',
        visivel: sessao.permissoes.includes('gerir_gabinetes'),
      },
      {
        href: '/auditoria',
        rotulo: 'Auditoria',
        visivel: sessao.permissoes.includes('ver_auditoria'),
      },
    ].filter((item) => item.visivel),
  );
</script>

<nav class="menu" aria-label="Menu principal">
  <ul>
    {#each itens as item (item.href)}
      <li>
        <a
          href={item.href}
          aria-current={caminho === item.href ||
          (item.href === '/processos' && caminho.startsWith('/processos/'))
            ? 'page'
            : undefined}
        >
          {item.rotulo}
        </a>
      </li>
    {/each}
  </ul>
</nav>

<style>
  .menu {
    background: var(--superficie);
    border-right: 1px solid var(--borda);
    min-width: 12rem;
    padding: 1rem 0;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  a {
    display: block;
    padding: 0.5rem 1.25rem;
    text-decoration: none;
    color: var(--texto);
  }
  a[aria-current='page'] {
    font-weight: 700;
    color: var(--primaria);
    border-left: 4px solid var(--primaria);
    padding-left: calc(1.25rem - 4px);
  }
</style>
