<script lang="ts">
  // Formulário de criação de usuário; só oferece os papéis que a sessão pode criar.
  import { chamar, mensagemErro } from '$lib/api';
  import type { PapelCriavel } from '$lib/permissoes';
  import { ROTULO_PAPEL, type Gabinete, type UsuarioComSenha } from '$lib/tipos';
  import Aviso from './Aviso.svelte';

  interface Props {
    papeis: PapelCriavel[];
    /** Lista de gabinetes para o administrador escolher; vazia = gabinete do próprio usuário. */
    gabinetes?: Gabinete[];
    titulo?: string;
    aoCriar: (criado: UsuarioComSenha) => void;
  }

  let { papeis, gabinetes = [], titulo = 'Novo usuário', aoCriar }: Props = $props();

  let nome = $state('');
  let papel = $state<PapelCriavel | ''>('');
  let gabineteId = $state('');
  let erro = $state('');
  let enviando = $state(false);
  const PADRAO_NOME = '[a-z0-9][a-z0-9._\\-]{2,63}';
  const idBase = `novo-${Math.random().toString(36).slice(2, 8)}`;

  const papelEfetivo = $derived(papel || papeis[0] || 'assessor');

  async function enviar(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    erro = '';
    enviando = true;
    try {
      const corpo: Record<string, string> = { nome_usuario: nome.trim(), papel: papelEfetivo };
      if (gabinetes.length > 0) corpo['gabinete_id'] = gabineteId;
      const criado = await chamar<UsuarioComSenha>('POST', '/usuarios', corpo);
      nome = '';
      aoCriar(criado);
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      enviando = false;
    }
  }
</script>

<form class="cartao" onsubmit={enviar} aria-labelledby="{idBase}-titulo">
  <h2 id="{idBase}-titulo">{titulo}</h2>
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
  <div class="campo">
    <label for="{idBase}-nome">Nome de usuário</label>
    <input
      id="{idBase}-nome"
      bind:value={nome}
      required
      minlength="3"
      maxlength="64"
      pattern={PADRAO_NOME}
      autocomplete="off"
      aria-describedby="{idBase}-dica"
    />
    <p class="dica" id="{idBase}-dica">3 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.</p>
  </div>
  {#if papeis.length > 1}
    <div class="campo">
      <label for="{idBase}-papel">Papel</label>
      <select id="{idBase}-papel" bind:value={papel}>
        {#each papeis as opcao (opcao)}
          <option value={opcao}>{ROTULO_PAPEL[opcao]}</option>
        {/each}
      </select>
    </div>
  {/if}
  {#if gabinetes.length > 0}
    <div class="campo">
      <label for="{idBase}-gabinete">Gabinete</label>
      <select id="{idBase}-gabinete" bind:value={gabineteId} required>
        <option value="" disabled>Escolha o gabinete</option>
        {#each gabinetes as gabinete (gabinete.id)}
          <option value={gabinete.id}>{gabinete.nome}</option>
        {/each}
      </select>
    </div>
  {/if}
  <button type="submit" disabled={enviando}>Criar {ROTULO_PAPEL[papelEfetivo].toLowerCase()}</button>
</form>
