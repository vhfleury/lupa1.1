<script lang="ts">
  import { goto } from '$app/navigation';
  import { chamar, ErroApi, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import { carregarSessao, sessao } from '$lib/sessao.svelte';

  let atual = $state('');
  let nova = $state('');
  let confirmacao = $state('');
  let erro = $state('');
  let enviando = $state(false);
  let primeiroCampo: HTMLInputElement | undefined = $state();

  const obrigatoria = $derived(sessao.atual?.troca_senha_obrigatoria ?? false);

  $effect(() => {
    primeiroCampo?.focus();
  });

  async function enviar(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    erro = '';
    if (nova !== confirmacao) {
      erro = 'A confirmação não confere com a nova senha.';
      return;
    }
    enviando = true;
    try {
      await chamar('POST', '/auth/trocar-senha', { senha_atual: atual, nova_senha: nova });
      await carregarSessao();
      await goto('/', { replaceState: true });
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401 && !e.sessaoExpirada) {
        erro = 'Senha atual incorreta.';
      } else {
        erro = mensagemErro(e);
      }
    } finally {
      atual = '';
      nova = '';
      confirmacao = '';
      enviando = false;
    }
  }

  async function sair(): Promise<void> {
    try {
      await chamar('POST', '/auth/logout', undefined, { tratarSessao: false });
    } catch {
      // Sessão já inválida.
    }
    sessao.definir(null);
    await goto('/login');
  }
</script>

<svelte:head><title>Trocar senha · Lupa</title></svelte:head>

<div class="cartao">
  <h1>Trocar senha</h1>
  {#if obrigatoria}
    <Aviso tipo="info">Antes de continuar, defina uma senha pessoal no lugar da senha temporária.</Aviso>
  {/if}
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
  <form onsubmit={enviar}>
    <div class="campo">
      <label for="senha_atual">Senha atual</label>
      <input
        id="senha_atual"
        type="password"
        bind:this={primeiroCampo}
        bind:value={atual}
        autocomplete="current-password"
        required
      />
    </div>
    <div class="campo">
      <label for="nova_senha">Nova senha</label>
      <input
        id="nova_senha"
        type="password"
        bind:value={nova}
        autocomplete="new-password"
        minlength="12"
        required
        aria-describedby="dica-senha"
      />
      <p class="dica" id="dica-senha">
        No mínimo 12 caracteres. Uma frase longa e fácil de lembrar é melhor que uma senha curta.
      </p>
    </div>
    <div class="campo">
      <label for="confirmacao">Confirme a nova senha</label>
      <input
        id="confirmacao"
        type="password"
        bind:value={confirmacao}
        autocomplete="new-password"
        minlength="12"
        required
      />
    </div>
    <div class="acoes">
      <button type="submit" disabled={enviando}>Salvar nova senha</button>
      <button type="button" class="secundario" onclick={sair}>Sair</button>
    </div>
  </form>
</div>
