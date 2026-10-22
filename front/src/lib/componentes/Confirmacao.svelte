<script lang="ts">
  // Confirmação de ação sensível (6.10): diálogo modal nativo, com foco em "Cancelar", Esc
  // cancela e o foco volta ao botão que abriu (comportamento do <dialog>).
  interface Props {
    aberto: boolean;
    titulo: string;
    mensagem: string;
    rotuloConfirmar: string;
    perigo?: boolean;
    aoConfirmar: () => void;
    aoCancelar: () => void;
  }

  let {
    aberto,
    titulo,
    mensagem,
    rotuloConfirmar,
    perigo = false,
    aoConfirmar,
    aoCancelar,
  }: Props = $props();

  let dialogo: HTMLDialogElement | undefined = $state();
  let cancelar: HTMLButtonElement | undefined = $state();

  $effect(() => {
    if (!dialogo) return;
    if (aberto && !dialogo.open) {
      if (typeof dialogo.showModal === 'function') dialogo.showModal();
      else dialogo.setAttribute('open', '');
      cancelar?.focus();
    } else if (!aberto && dialogo.open) {
      if (typeof dialogo.close === 'function') dialogo.close();
      else dialogo.removeAttribute('open');
    }
  });

  function aoFechar(evento: Event): void {
    evento.preventDefault();
    aoCancelar();
  }
</script>

<dialog
  bind:this={dialogo}
  aria-labelledby="confirmacao-titulo"
  aria-describedby="confirmacao-mensagem"
  oncancel={aoFechar}
  data-testid="confirmacao"
>
  <h2 id="confirmacao-titulo">{titulo}</h2>
  <p id="confirmacao-mensagem">{mensagem}</p>
  <div class="acoes">
    <button type="button" class={perigo ? 'perigo' : ''} onclick={aoConfirmar}>
      {rotuloConfirmar}
    </button>
    <button type="button" class="secundario" bind:this={cancelar} onclick={aoCancelar}>
      Cancelar
    </button>
  </div>
</dialog>

<style>
  dialog {
    border: 1px solid var(--borda);
    border-radius: var(--raio);
    background: var(--superficie);
    color: var(--texto);
    max-width: 28rem;
    padding: 1.25rem;
  }
  dialog::backdrop {
    background: rgb(0 0 0 / 50%);
  }
  h2 {
    margin-top: 0;
  }
  .acoes {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
</style>
