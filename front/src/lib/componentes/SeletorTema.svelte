<script lang="ts">
  // Seletor de tema (claro, escuro, do sistema); a escolha fica só no localStorage.
  import { escolherTema, lerTema, TEMAS, type Tema } from '$lib/tema';

  let { id = 'tema' }: { id?: string } = $props();

  let tema = $state<Tema>(lerTema());

  function mudar(evento: Event): void {
    tema = (evento.currentTarget as HTMLSelectElement).value as Tema;
    escolherTema(tema);
  }
</script>

<div class="seletor">
  <label for={id}>Tema</label>
  <select {id} value={tema} onchange={mudar} data-testid="seletor-tema">
    {#each TEMAS as opcao (opcao.valor)}
      <option value={opcao.valor}>{opcao.rotulo}</option>
    {/each}
  </select>
</div>

<style>
  .seletor {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  label {
    margin: 0;
    font-weight: 400;
    font-size: 0.9rem;
  }
  select {
    width: auto;
  }
</style>
