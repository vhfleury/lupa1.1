<script lang="ts">
  // Gestão de usuários. Desembargador: assessores do próprio gabinete. Administrador: todos.
  // Botões que o papel não tem não aparecem; o servidor reconfere cada ação.
  import { onMount } from 'svelte';
  import { chamar, mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import Confirmacao from '$lib/componentes/Confirmacao.svelte';
  import FormNovoUsuario from '$lib/componentes/FormNovoUsuario.svelte';
  import SenhaTemporaria from '$lib/componentes/SenhaTemporaria.svelte';
  import { acoesSobre, gereUsuarios, papeisCriaveis } from '$lib/permissoes';
  import { sessao, tem } from '$lib/sessao.svelte';
  import {
    ROTULO_PAPEL,
    type Gabinete,
    type Usuario,
    type UsuarioComSenha,
  } from '$lib/tipos';

  type Acao = 'desativar' | 'reativar' | 'resetar-senha' | 'resetar-mfa';

  const MENSAGENS: Record<Acao, string> = {
    desativar: 'desativado',
    reativar: 'reativado',
    'resetar-senha': 'com senha temporária nova',
    'resetar-mfa': 'com autenticador apagado; o próximo login cadastra outro',
  };

  let usuarios = $state<Usuario[]>([]);
  let gabinetes = $state<Gabinete[]>([]);
  let erro = $state('');
  let aviso = $state('');
  let carregando = $state(true);
  let senhaMostrada = $state<{ nome: string; senha: string } | null>(null);
  // 6.10: desativar pede confirmação (corta o acesso do usuário na hora).
  let paraDesativar = $state<Usuario | null>(null);

  async function confirmarDesativacao(): Promise<void> {
    const alvo = paraDesativar;
    paraDesativar = null;
    if (alvo) await agir(alvo, 'desativar');
  }

  const atual = $derived(sessao.atual);
  const ehAdmin = $derived(tem(atual, 'gerir_gabinetes'));
  const papeis = $derived(papeisCriaveis(atual));

  async function carregar(): Promise<void> {
    try {
      usuarios = await chamar<Usuario[]>('GET', '/usuarios');
      if (ehAdmin) gabinetes = await chamar<Gabinete[]>('GET', '/gabinetes');
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      carregando = false;
    }
  }

  onMount(() => {
    if (gereUsuarios(atual)) void carregar();
    else carregando = false;
  });

  function nomeGabinete(id: string | null): string {
    if (id === null) return '—';
    return gabinetes.find((g) => g.id === id)?.nome ?? id;
  }

  function mostrarSenha(criado: UsuarioComSenha): void {
    senhaMostrada = { nome: criado.nome_usuario, senha: criado.senha_temporaria };
  }

  async function aoCriar(criado: UsuarioComSenha): Promise<void> {
    erro = '';
    aviso = `Usuário ${criado.nome_usuario} criado.`;
    mostrarSenha(criado);
    await carregar();
  }

  async function agir(alvo: Usuario, acao: Acao): Promise<void> {
    erro = '';
    aviso = '';
    try {
      const resposta = await chamar<Usuario | UsuarioComSenha>(
        'POST',
        `/usuarios/${alvo.id}/${acao}`,
      );
      if ('senha_temporaria' in resposta) mostrarSenha(resposta);
      aviso = `Usuário ${alvo.nome_usuario} ${MENSAGENS[acao]}.`;
      await carregar();
    } catch (e) {
      erro = mensagemErro(e);
    }
  }
</script>

<svelte:head><title>Usuários · Lupa</title></svelte:head>

<h1>Usuários</h1>

{#if !gereUsuarios(atual)}
  <Aviso tipo="erro">Seu papel não dá acesso à gestão de usuários.</Aviso>
{:else}
  {#if senhaMostrada}
    <SenhaTemporaria
      nomeUsuario={senhaMostrada.nome}
      senha={senhaMostrada.senha}
      aoFechar={() => (senhaMostrada = null)}
    />
  {/if}
  {#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
  {#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

  {#if carregando}
    <p role="status">Carregando…</p>
  {:else}
    <table>
      <caption class="visualmente-oculto">Usuários {ehAdmin ? 'de todos os gabinetes' : 'do gabinete'}</caption>
      <thead>
        <tr>
          <th scope="col">Usuário</th>
          <th scope="col">Papel</th>
          {#if ehAdmin}<th scope="col">Gabinete</th>{/if}
          <th scope="col">Situação</th>
          <th scope="col">Autenticador</th>
          <th scope="col">Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each usuarios as usuario (usuario.id)}
          {@const acoes = acoesSobre(atual, usuario)}
          <tr data-testid="linha-usuario" data-usuario={usuario.nome_usuario}>
            <th scope="row">{usuario.nome_usuario}</th>
            <td>{ROTULO_PAPEL[usuario.papel]}</td>
            {#if ehAdmin}<td>{nomeGabinete(usuario.gabinete_id)}</td>{/if}
            <td data-testid="situacao">
              {usuario.ativo ? 'Ativo' : 'Inativo'}{usuario.troca_senha_obrigatoria
                ? ' · troca de senha pendente'
                : ''}
            </td>
            <td>{usuario.mfa_confirmado ? 'Cadastrado' : 'Pendente'}</td>
            <td>
              <div class="acoes">
                {#if acoes.gerir}
                  {#if usuario.ativo}
                    <button
                      type="button"
                      class="perigo"
                      aria-label="Desativar {usuario.nome_usuario}"
                      onclick={() => (paraDesativar = usuario)}>Desativar</button
                    >
                  {:else}
                    <button
                      type="button"
                      class="secundario"
                      aria-label="Reativar {usuario.nome_usuario}"
                      onclick={() => agir(usuario, 'reativar')}>Reativar</button
                    >
                  {/if}
                {/if}
                {#if acoes.resetar}
                  <button
                    type="button"
                    class="secundario"
                    aria-label="Resetar senha de {usuario.nome_usuario}"
                    onclick={() => agir(usuario, 'resetar-senha')}>Resetar senha</button
                  >
                  <button
                    type="button"
                    class="secundario"
                    aria-label="Resetar autenticador de {usuario.nome_usuario}"
                    onclick={() => agir(usuario, 'resetar-mfa')}>Resetar autenticador</button
                  >
                {/if}
              </div>
            </td>
          </tr>
        {:else}
          <tr><td colspan={ehAdmin ? 6 : 5}>Nenhum usuário.</td></tr>
        {/each}
      </tbody>
    </table>

    <div class="novo">
      <FormNovoUsuario
        {papeis}
        gabinetes={ehAdmin ? gabinetes : []}
        titulo={ehAdmin ? 'Novo usuário' : 'Novo assessor'}
        {aoCriar}
      />
    </div>
  {/if}
{/if}

<Confirmacao
  aberto={paraDesativar !== null}
  titulo="Desativar usuário?"
  mensagem={`${paraDesativar?.nome_usuario ?? ''} perde o acesso imediatamente e as sessões abertas são encerradas. Dá para reativar depois.`}
  rotuloConfirmar="Desativar"
  perigo
  aoConfirmar={confirmarDesativacao}
  aoCancelar={() => (paraDesativar = null)}
/>

<style>
  .novo {
    margin-top: 1.5rem;
    max-width: 30rem;
  }
</style>
