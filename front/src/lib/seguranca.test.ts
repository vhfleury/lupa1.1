// Etapa 6.10 (prompt-injection.md, seção 6): nada que venha dos autos vira HTML, Markdown ou
// link clicável. Dois níveis: (1) componente real com trecho hostil sai como texto; (2) varredura
// das fontes: nenhum {@html}, innerHTML, renderizador de Markdown nem link montado com texto.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { Mensagem } from './chat/chat';
import MensagemChat from './chat/MensagemChat.svelte';

const HOSTIL =
  'intimei o defensor <script>window.__xss = 1</script> [link](http://x) http://exemplo ' +
  '<img src=x onerror="window.__xss=2">';

function mensagem(parcial: Partial<Mensagem>): Mensagem {
  return {
    mensagem_id: 'm1',
    papel: 'agente',
    status: 'respondida',
    texto: HOSTIL,
    citacoes: [
      {
        pagina_id: 'p1',
        trecho: HOSTIL,
        hash_trecho: 'a'.repeat(64),
        pagina_numero: 3,
        arquivo_id: 'arq',
      },
      {
        pagina_id: 'p2',
        trecho: HOSTIL,
        hash_trecho: 'b'.repeat(64),
        pagina_numero: null,
        arquivo_id: null,
      },
    ],
    avisos: [HOSTIL],
    citacoes_descartadas: 0,
    rotulo: 'gerado por IA',
    criado_em: null,
    ...parcial,
  };
}

describe('conteúdo dos autos é sempre texto', () => {
  it('trecho com <script>, Markdown e URL sai literal, sem elemento nem link externo', () => {
    const { container } = render(MensagemChat, { processoId: 'proc', mensagem: mensagem({}) });
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    const links = [...container.querySelectorAll('a')];
    // Só o link interno da citação (montado pelo front com ids), nunca a URL do texto.
    expect(links).toHaveLength(1);
    expect(links[0]?.getAttribute('href')).toBe(
      '/processos/proc/visualizador?arquivo=arq&pagina=3',
    );
    for (const a of links) expect(a.getAttribute('href')).not.toMatch(/^https?:/);
    expect(container.textContent).toContain('<script>window.__xss = 1</script>');
    expect(container.textContent).toContain('[link](http://x)');
    expect(container.textContent).toContain('http://exemplo');
    expect(screen.getAllByText(/\[link\]\(http:\/\/x\)/).length).toBeGreaterThan(0);
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it('pergunta do usuário com HTML também sai como texto', () => {
    const { container } = render(MensagemChat, {
      processoId: 'proc',
      mensagem: mensagem({ papel: 'usuario', citacoes: [], avisos: [] }),
    });
    expect(container.querySelector('script, img, a')).toBeNull();
    expect(container.textContent).toContain('[link](http://x)');
  });
});

function fontes(dir: string): string[] {
  return readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) return fontes(caminho);
    return /\.(svelte|ts)$/.test(nome) && !nome.endsWith('.test.ts') ? [caminho] : [];
  });
}

describe('varredura das fontes do front', () => {
  const arquivos = fontes('src');

  it('acha as fontes', () => {
    expect(arquivos.length).toBeGreaterThan(20);
  });

  it.each([
    ['{@html', /\{@html/],
    ['innerHTML/outerHTML/insertAdjacentHTML', /\b(innerHTML|outerHTML|insertAdjacentHTML)\b/],
    ['document.write', /document\.write/],
    ['renderizador de Markdown', /from ['"](marked|markdown-it|micromark|showdown|remark)/],
    ['linkify', /linkify/i],
    ['href montado com trecho ou texto', /href=\{[^}]*\b(trecho|texto|descricao|conteudo)\b/],
  ])('nenhuma fonte usa %s', (_nome, padrao) => {
    const achados = arquivos.filter((arquivo) => padrao.test(readFileSync(arquivo, 'utf8')));
    expect(achados).toEqual([]);
  });

  it('nenhum atributo style inline (a CSP bloqueia; use style: ou classe)', () => {
    const achados = arquivos.filter(
      (arquivo) =>
        arquivo.endsWith('.svelte') && /\sstyle=["{]/.test(readFileSync(arquivo, 'utf8')),
    );
    expect(achados).toEqual([]);
  });
});
