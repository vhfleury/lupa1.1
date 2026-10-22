import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import {
  conversaAtual,
  linkCitacao,
  plural,
  rotuloStatus,
  type Citacao,
  type Conversa,
  type Mensagem,
} from './chat';
import MensagemChat from './MensagemChat.svelte';

const CITACAO: Citacao = {
  pagina_id: 'p1',
  trecho: 'intimei o defensor',
  hash_trecho: 'a'.repeat(64),
  pagina_numero: 3,
  arquivo_id: 'arq',
};

function mensagem(parcial: Partial<Mensagem>): Mensagem {
  return {
    mensagem_id: 'm1',
    papel: 'agente',
    status: 'respondida',
    texto: 'A defesa foi intimada.',
    citacoes: [],
    avisos: [],
    citacoes_descartadas: 0,
    rotulo: 'gerado por IA',
    criado_em: null,
    ...parcial,
  };
}

describe('regras do chat', () => {
  it('link da citação leva à página do visualizador com arquivo e número (sem trecho na URL)', () => {
    const link = linkCitacao('proc', CITACAO);
    expect(link).toMatch(/^\/processos\/proc\/visualizador\?/);
    const busca = new URLSearchParams(link?.split('?')[1]);
    expect(busca.get('arquivo')).toBe('arq');
    expect(busca.get('pagina')).toBe('3');
    expect(busca.get('trecho')).toBeNull(); // 6.10: nada dos autos na URL
    expect(linkCitacao('proc', { ...CITACAO, arquivo_id: null })).toBe(
      '/processos/proc/visualizador?pagina=3',
    );
    expect(linkCitacao('proc', { ...CITACAO, pagina_numero: null, arquivo_id: null })).toBeNull();
  });

  it('rótulos destacam os desfechos que não são resposta conferida', () => {
    expect(rotuloStatus('respondida')).toBeNull();
    expect(rotuloStatus('sem_evidencia')).toMatch(/Sem citação válida/);
    expect(rotuloStatus('recusa')).toMatch(/fora/);
    expect(rotuloStatus('descartada')).toMatch(/descartada/);
    expect(rotuloStatus('teto')).toMatch(/Limite/);
    expect(rotuloStatus('pergunta')).toBeNull();
  });

  it('conversa atual é a última não encerrada', () => {
    const base: Conversa = {
      conversa_id: 'c1',
      criada_em: '',
      encerrada: false,
      motivo_encerramento: null,
      citacoes_descartadas: 0,
      mensagens: [],
    };
    expect(conversaAtual([])).toBeNull();
    expect(conversaAtual([base])?.conversa_id).toBe('c1');
    expect(conversaAtual([base, { ...base, conversa_id: 'c2', encerrada: true }])).toBeNull();
    expect(plural(1, 'item', 'itens')).toBe('1 item');
    expect(plural(2, 'item', 'itens')).toBe('2 itens');
  });
});

describe('MensagemChat', () => {
  it('resposta com citação: aviso de IA e link para a página', () => {
    render(MensagemChat, {
      processoId: 'proc',
      mensagem: mensagem({ citacoes: [CITACAO], citacoes_descartadas: 1 }),
    });
    expect(screen.getByTestId('aviso-ia')).toHaveTextContent(/gerado por IA/);
    expect(screen.getByTestId('citacao')).toHaveAttribute(
      'href',
      expect.stringContaining('/processos/proc/visualizador?arquivo=arq&pagina=3'),
    );
    expect(screen.getByTestId('descartes')).toHaveTextContent('1 citação descartada');
    expect(screen.queryByTestId('desfecho')).toBeNull();
  });

  it('resposta sem citação válida aparece marcada', () => {
    render(MensagemChat, {
      processoId: 'proc',
      mensagem: mensagem({ status: 'sem_evidencia', avisos: ['Resposta sem evidência.'] }),
    });
    expect(screen.getByTestId('desfecho')).toHaveTextContent(/Sem citação válida/);
    expect(screen.getByText('Resposta sem evidência.')).toBeInTheDocument();
  });

  it('pergunta do usuário não leva aviso de IA', () => {
    render(MensagemChat, {
      processoId: 'proc',
      mensagem: mensagem({ papel: 'usuario', status: 'pergunta', rotulo: null }),
    });
    expect(screen.queryByTestId('aviso-ia')).toBeNull();
  });
});
