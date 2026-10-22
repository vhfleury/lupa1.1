<script lang="ts">
  // Mostra a senha temporária uma única vez; ao confirmar, o valor sai da memória da tela.
  interface Props {
    nomeUsuario: string;
    senha: string;
    aoFechar: () => void;
  }

  let { nomeUsuario, senha, aoFechar }: Props = $props();
  let botao: HTMLButtonElement | undefined = $state();

  $effect(() => {
    botao?.focus();
  });
</script>

<section class="cartao destaque" aria-labelledby="titulo-senha-temporaria" data-testid="senha-temporaria">
  <h2 id="titulo-senha-temporaria">Senha temporária de {nomeUsuario}</h2>
  <p>
    Entregue esta senha pessoalmente. Ela <strong>não será exibida de novo</strong>; no primeiro
    acesso a pessoa cadastra o autenticador e troca a senha.
  </p>
  <p class="mono senha" data-testid="senha-temporaria-valor">{senha}</p>
  <button type="button" bind:this={botao} onclick={aoFechar}>Já anotei, fechar</button>
</section>

<style>
  .destaque {
    border-color: var(--primaria);
    border-width: 2px;
    margin-bottom: 1.5rem;
  }
  .senha {
    font-size: 1.25rem;
    padding: 0.5rem;
    background: var(--fundo);
    border-radius: var(--raio);
  }
</style>
