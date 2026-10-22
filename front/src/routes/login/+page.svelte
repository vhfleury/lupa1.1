<script lang="ts">
  // Login em dois passos: senha → código TOTP (ou cadastro do autenticador no primeiro acesso).
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { chamar, mensagemCodigo, mensagemLogin } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import QrCode from '$lib/componentes/QrCode.svelte';
  import type { RespostaLogin, RespostaMfa } from '$lib/tipos';

  type Etapa = { tipo: 'senha' } | { tipo: 'codigo'; resposta: RespostaLogin };

  let etapa = $state<Etapa>({ tipo: 'senha' });
  let nome = $state('');
  let senha = $state('');
  let codigo = $state('');
  let erro = $state('');
  let enviando = $state(false);
  let campoInicial: HTMLInputElement | undefined = $state();
  let campoCodigo: HTMLInputElement | undefined = $state();

  const expirada = $derived(page.url.searchParams.get('motivo') === 'expirada');

  $effect(() => {
    if (etapa.tipo === 'senha') campoInicial?.focus();
    else campoCodigo?.focus();
  });

  async function enviarSenha(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    erro = '';
    enviando = true;
    try {
      const resposta = await chamar<RespostaLogin>(
        'POST',
        '/auth/login',
        { nome_usuario: nome.trim(), senha },
        { tratarSessao: false },
      );
      senha = '';
      codigo = '';
      etapa = { tipo: 'codigo', resposta };
    } catch (e) {
      senha = '';
      erro = mensagemLogin(e);
    } finally {
      enviando = false;
    }
  }

  async function enviarCodigo(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    if (etapa.tipo !== 'codigo') return;
    erro = '';
    enviando = true;
    const rota = etapa.resposta.etapa === 'configurar_mfa' ? '/auth/mfa/confirmar' : '/auth/mfa';
    try {
      const resultado = await chamar<RespostaMfa>(
        'POST',
        rota,
        { desafio: etapa.resposta.desafio, codigo: codigo.trim() },
        { tratarSessao: false },
      );
      await goto(resultado.troca_senha_obrigatoria ? '/trocar-senha' : '/', { replaceState: true });
    } catch (e) {
      codigo = '';
      erro = mensagemCodigo(e);
    } finally {
      enviando = false;
    }
  }

  function recomecar(): void {
    etapa = { tipo: 'senha' };
    erro = '';
    codigo = '';
  }
</script>

<svelte:head><title>Entrar · Lupa</title></svelte:head>

<div class="cartao">
  <h1>Lupa</h1>
  {#if expirada && etapa.tipo === 'senha'}
    <Aviso tipo="info">Sessão encerrada ou expirada. Entre novamente.</Aviso>
  {/if}
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}

  {#if etapa.tipo === 'senha'}
    <form onsubmit={enviarSenha} aria-label="Entrar">
      <div class="campo">
        <label for="nome_usuario">Usuário</label>
        <input
          id="nome_usuario"
          bind:this={campoInicial}
          bind:value={nome}
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
          required
          maxlength="64"
        />
      </div>
      <div class="campo">
        <label for="senha">Senha</label>
        <input
          id="senha"
          type="password"
          bind:value={senha}
          autocomplete="current-password"
          required
          maxlength="256"
        />
      </div>
      <button type="submit" disabled={enviando}>Continuar</button>
    </form>
  {:else}
    {@const resposta = etapa.resposta}
    {#if resposta.etapa === 'configurar_mfa'}
      <h2>Cadastre o autenticador</h2>
      <ol class="passos">
        <li>Abra o aplicativo autenticador no celular (por exemplo, Google Authenticator ou Aegis).</li>
        <li>Leia o QR code abaixo ou digite a chave manualmente.</li>
        <li>Digite o código de 6 dígitos que o aplicativo mostrar.</li>
      </ol>
      <div class="qr">
        <QrCode texto={resposta.uri_qr} rotulo="QR code para cadastrar o autenticador do Lupa" />
      </div>
      <p>
        Chave para digitação:
        <span class="mono chave" data-testid="segredo-mfa">{resposta.segredo}</span>
      </p>
      <details>
        <summary>Endereço completo do cadastro (otpauth)</summary>
        <p class="mono" data-testid="uri-mfa">{resposta.uri_qr}</p>
      </details>
    {:else}
      <h2>Verificação em duas etapas</h2>
      <p>Digite o código de 6 dígitos do seu aplicativo autenticador.</p>
    {/if}
    <form onsubmit={enviarCodigo} aria-label="Código do autenticador">
      <div class="campo">
        <label for="codigo">Código de 6 dígitos</label>
        <input
          id="codigo"
          bind:this={campoCodigo}
          bind:value={codigo}
          inputmode="numeric"
          autocomplete="one-time-code"
          pattern={'[0-9]{6}'}
          maxlength="6"
          required
        />
      </div>
      <div class="acoes">
        <button type="submit" disabled={enviando}>
          {resposta.etapa === 'configurar_mfa' ? 'Confirmar autenticador' : 'Entrar'}
        </button>
        <button type="button" class="secundario" onclick={recomecar}>Voltar</button>
      </div>
    </form>
  {/if}
</div>

<style>
  .qr {
    display: flex;
    justify-content: center;
    margin: 1rem 0;
  }
  .chave {
    display: inline-block;
    font-size: 1.05rem;
    letter-spacing: 0.05em;
  }
  .passos {
    padding-left: 1.25rem;
  }
</style>
