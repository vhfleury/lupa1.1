<script lang="ts">
  // Mensagem acessível: erros são anunciados de imediato (role=alert); o resto, educadamente.
  import type { Snippet } from 'svelte';

  interface Props {
    tipo?: 'erro' | 'sucesso' | 'info';
    children: Snippet;
  }

  let { tipo = 'info', children }: Props = $props();
</script>

<div class="aviso {tipo}" role={tipo === 'erro' ? 'alert' : 'status'}>
  {@render children()}
</div>

<style>
  .aviso {
    border-radius: var(--raio);
    padding: 0.6rem 0.8rem;
    margin: 0 0 1rem;
    border: 1px solid transparent;
  }
  .erro {
    background: var(--perigo-fundo);
    color: var(--perigo);
    border-color: var(--perigo);
  }
  .sucesso {
    background: var(--sucesso-fundo);
    color: var(--sucesso);
    border-color: var(--sucesso);
  }
  .info {
    background: var(--aviso-fundo);
    color: var(--aviso-texto);
  }
</style>
