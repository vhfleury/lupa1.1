<script lang="ts">
  // Chat sobre os autos (Etapa 6.8). Pergunta → resposta com citações conferidas (cada uma abre
  // a página no visualizador), recusa explicada, teto, contador de descartes e histórico das
  // conversas do usuário. Processo em revisão (incidente de injeção): aviso, chat suspenso e,
  // para desembargador ou administrador, o botão de liberar (o servidor reconfere o papel).
  import { onMount, tick } from 'svelte';
  import { page } from '$app/state';
  import { mensagemErro } from '$lib/api';
  import Aviso from '$lib/componentes/Aviso.svelte';
  import Confirmacao from '$lib/componentes/Confirmacao.svelte';
  import {
    apiChat,
    conversaAtual,
    MOTIVO_ENCERRAMENTO,
    MOTIVO_REVISAO,
    plural,
    type Conversa,
    type SituacaoRevisao,
  } from '$lib/chat/chat';
  import MensagemChat from '$lib/chat/MensagemChat.svelte';
  import { sessao, tem } from '$lib/sessao.svelte';

  const LIMITE_PERGUNTA = 2000;

  const processoId = $derived(page.params['id'] ?? '');
  let conversas = $state<Conversa[]>([]);
  let revisao = $state<SituacaoRevisao | null>(null);
  let pergunta = $state('');
  let erro = $state('');
  let aviso = $state('');
  let carregando = $state(true);
  let enviando = $state(false);
  let campo = $state<HTMLTextAreaElement | null>(null);
  // 6.10: liberar a revisão pede confirmação (reabre chat e resumos do processo).
  let confirmandoLiberacao = $state(false);

  const atual = $derived(conversaAtual(conversas));
  const anteriores = $derived([...conversas.filter((c) => c !== atual)].reverse());
  const podeLiberar = $derived(tem(sessao.atual, 'ver_auditoria'));
  const emRevisao = $derived(revisao?.em_revisao === true);

  async function carregar(): Promise<void> {
    try {
      const [historico, situacao] = await Promise.all([
        apiChat.historico(processoId),
        apiChat.revisao(processoId),
      ]);
      conversas = historico.conversas;
      revisao = situacao;
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      carregando = false;
    }
  }

  onMount(() => {
    void carregar();
  });

  async function enviar(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    const texto = pergunta.trim();
    if (!texto || enviando) return;
    erro = '';
    aviso = '';
    enviando = true;
    try {
      await apiChat.perguntar(processoId, texto);
      pergunta = '';
      await carregar();
      await tick();
      campo?.focus();
    } catch (e) {
      erro = mensagemErro(e);
    } finally {
      enviando = false;
    }
  }

  async function liberar(): Promise<void> {
    confirmandoLiberacao = false;
    erro = '';
    try {
      revisao = await apiChat.liberar(processoId);
      aviso = 'Processo liberado. O chat e os resumos voltam a funcionar.';
    } catch (e) {
      erro = mensagemErro(e);
    }
  }
</script>

<svelte:head><title>Chat do processo · Lupa</title></svelte:head>

<h1>Chat sobre os autos</h1>
<p class="contexto">
  As respostas vêm só dos autos deste processo, com citação da página. O assistente não valora
  prova, não tipifica, não conclui sobre norma e não opina sobre o resultado.
</p>

{#if erro}<Aviso tipo="erro">{erro}</Aviso>{/if}
{#if aviso}<Aviso tipo="sucesso">{aviso}</Aviso>{/if}

{#if emRevisao && revisao}
  <div class="revisao" role="alert" data-testid="processo-em-revisao">
    <strong>Processo em revisão.</strong>
    Uma resposta do assistente foi bloqueada porque {MOTIVO_REVISAO[revisao.motivo ?? ''] ??
      'violou a conferência automática'}. O chat e os resumos gerados ficam suspensos até um
    desembargador ou o administrador liberar.
    {#if podeLiberar}
      <button type="button" onclick={() => (confirmandoLiberacao = true)}>Liberar revisão</button>
    {/if}
  </div>
{/if}

{#if carregando}
  <p role="status">Carregando conversas…</p>
{:else}
  <section aria-labelledby="titulo-atual">
    <h2 id="titulo-atual">Conversa atual</h2>
    {#if atual}
      <p class="contador" data-testid="descartes-conversa">
        {plural(
          atual.citacoes_descartadas,
          'citação descartada nesta conversa',
          'citações descartadas nesta conversa',
        )}
      </p>
      <div aria-live="polite" data-testid="conversa-atual">
        {#each atual.mensagens as m (m.mensagem_id)}
          <MensagemChat processoId={processoId} mensagem={m} />
        {/each}
      </div>
    {:else}
      <p>Nenhuma conversa aberta. A próxima pergunta abre uma conversa nova.</p>
    {/if}

    <form onsubmit={enviar} class="pergunta">
      <label for="pergunta">Pergunta</label>
      <textarea
        id="pergunta"
        bind:this={campo}
        bind:value={pergunta}
        maxlength={LIMITE_PERGUNTA}
        rows="3"
        disabled={emRevisao || enviando}
        placeholder="Ex.: Em que página está a certidão de intimação da defesa?"
      ></textarea>
      <div class="acoes">
        <span class="restante">{LIMITE_PERGUNTA - pergunta.length} caracteres restantes</span>
        <button type="submit" disabled={emRevisao || enviando || !pergunta.trim()}>
          {enviando ? 'Consultando…' : 'Perguntar'}
        </button>
      </div>
    </form>
  </section>

  <section aria-labelledby="titulo-historico">
    <h2 id="titulo-historico">Conversas anteriores</h2>
    {#if anteriores.length === 0}
      <p>Nenhuma conversa anterior neste processo.</p>
    {:else}
      {#each anteriores as conversa (conversa.conversa_id)}
        <details class="anterior" data-testid="conversa-anterior">
          <summary>
            Conversa de {new Date(conversa.criada_em).toLocaleString('pt-BR')}
            — {plural(conversa.mensagens.length, 'mensagem', 'mensagens')}
            {#if conversa.motivo_encerramento}
              (encerrada: {MOTIVO_ENCERRAMENTO[conversa.motivo_encerramento] ??
                conversa.motivo_encerramento})
            {/if}
          </summary>
          {#each conversa.mensagens as m (m.mensagem_id)}
            <MensagemChat processoId={processoId} mensagem={m} />
          {/each}
        </details>
      {/each}
    {/if}
  </section>
{/if}

<Confirmacao
  aberto={confirmandoLiberacao}
  titulo="Liberar a revisão?"
  mensagem="Confirme que conferiu o incidente. O chat e os resumos gerados voltam a funcionar neste processo, e a liberação fica registrada na auditoria."
  rotuloConfirmar="Liberar"
  aoConfirmar={liberar}
  aoCancelar={() => (confirmandoLiberacao = false)}
/>

<style>
  .contexto {
    color: var(--texto-suave);
    margin-top: 0;
  }
  .revisao {
    border: 2px solid var(--perigo);
    background: var(--perigo-fundo);
    color: var(--perigo);
    border-radius: var(--raio);
    padding: 0.75rem 1rem;
    margin: 0 0 1rem;
  }
  .revisao button {
    margin-left: 0.5rem;
  }
  .contador {
    color: var(--texto-suave);
    font-size: 0.9rem;
  }
  .pergunta textarea {
    width: 100%;
    font: inherit;
    padding: 0.5rem;
    border: 1px solid var(--borda);
    border-radius: var(--raio);
    background: var(--superficie);
    color: var(--texto);
  }
  .acoes {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.5rem;
  }
  .restante {
    font-size: 0.85rem;
    color: var(--texto-suave);
  }
  .anterior {
    margin-bottom: 0.75rem;
  }
  summary {
    cursor: pointer;
    margin-bottom: 0.5rem;
  }
</style>
