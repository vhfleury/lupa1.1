<script lang="ts">
  // Uma mensagem do chat. Resposta do agente: aviso de conteúdo gerado sempre visível, desfecho
  // marcado (sem evidência, recusa, descartada, teto), citações clicáveis para a página e o
  // contador de citações descartadas. Texto só como texto (nada de HTML do servidor).
  import { AVISO_IA, linkCitacao, plural, rotuloStatus, type Mensagem } from './chat';

  interface Props {
    processoId: string;
    mensagem: Mensagem;
  }

  let { processoId, mensagem }: Props = $props();

  const doAgente = $derived(mensagem.papel === 'agente');
  const rotulo = $derived(doAgente ? rotuloStatus(mensagem.status) : null);
</script>

<article
  class="mensagem {mensagem.papel} {mensagem.status}"
  data-testid="mensagem"
  data-status={mensagem.status}
  aria-label={doAgente ? 'Resposta do assistente' : 'Sua pergunta'}
>
  {#if doAgente}
    <p class="ia" data-testid="aviso-ia">{AVISO_IA}</p>
    {#if rotulo}
      <p class="desfecho" data-testid="desfecho">{rotulo}</p>
    {/if}
  {/if}
  <p class="texto">{mensagem.texto}</p>
  {#if doAgente && mensagem.citacoes.length > 0}
    <ol class="citacoes" aria-label="Citações conferidas">
      {#each mensagem.citacoes as citacao, i (`${citacao.pagina_id}-${i}`)}
        {@const destino = linkCitacao(processoId, citacao)}
        <li>
          {#if destino}
            <a href={destino} data-testid="citacao">
              Página {citacao.pagina_numero}: “{citacao.trecho}”
            </a>
          {:else}
            <span>“{citacao.trecho}” (página indisponível)</span>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
  {#if doAgente && mensagem.citacoes_descartadas > 0}
    <p class="descartes" data-testid="descartes">
      {plural(
        mensagem.citacoes_descartadas,
        'citação descartada nesta resposta',
        'citações descartadas nesta resposta',
      )}
      (não conferiram com o texto da página).
    </p>
  {/if}
  {#if doAgente}
    {#each mensagem.avisos.filter((a) => !a.includes('não conferiram')) as aviso (aviso)}
      <p class="aviso-msg">{aviso}</p>
    {/each}
  {/if}
</article>

<style>
  .mensagem {
    border: 1px solid var(--borda);
    border-radius: var(--raio);
    padding: 0.75rem 1rem;
    margin: 0 0 0.75rem;
    background: var(--superficie);
  }
  .usuario {
    border-left: 4px solid var(--primaria);
  }
  .agente {
    border-left: 4px solid var(--texto-suave);
  }
  .sem_evidencia,
  .descartada,
  .teto {
    border-left-color: var(--perigo);
  }
  .recusa {
    border-left-color: var(--foco);
  }
  .ia {
    margin: 0 0 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--aviso-texto);
    background: var(--aviso-fundo);
    padding: 0.2rem 0.5rem;
    border-radius: var(--raio);
    display: inline-block;
  }
  .desfecho {
    margin: 0 0 0.4rem;
    font-weight: 700;
    color: var(--perigo);
  }
  .texto {
    margin: 0;
    white-space: pre-wrap;
  }
  .citacoes {
    margin: 0.5rem 0 0;
    padding-left: 1.25rem;
  }
  .descartes,
  .aviso-msg {
    margin: 0.4rem 0 0;
    font-size: 0.9rem;
    color: var(--texto-suave);
  }
</style>
