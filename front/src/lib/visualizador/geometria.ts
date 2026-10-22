// Geometria do destaque: o servidor devolve retângulos em fração da página (origem no canto
// superior esquerdo); o cliente só os posiciona em porcentagem sobre a imagem renderizada.
import type { Retangulo } from '$lib/processos/tipos';

export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 3;
export const PASSO_ZOOM = 0.25;

function limitar(valor: number, minimo: number, maximo: number): number {
  return Math.min(Math.max(valor, minimo), maximo);
}

/** Estilo CSS (porcentagens) do retângulo sobre a imagem; nada sai da página. */
/** Posição do destaque em porcentagens da página (aplicada por `style:`, sem atributo inline). */
export function retanguloDestaque(r: Retangulo): {
  left: string;
  top: string;
  width: string;
  height: string;
} {
  const x = limitar(r.x, 0, 1);
  const y = limitar(r.y, 0, 1);
  const largura = limitar(r.largura, 0, 1 - x);
  const altura = limitar(r.altura, 0, 1 - y);
  const pct = (v: number): string => `${(v * 100).toFixed(3)}%`;
  return { left: pct(x), top: pct(y), width: pct(largura), height: pct(altura) };
}

export function estiloDestaque(r: Retangulo): string {
  const { left, top, width, height } = retanguloDestaque(r);
  return `left:${left};top:${top};width:${width};height:${height}`;
}

export function proximoZoom(atual: number, direcao: 1 | -1): number {
  return limitar(Math.round((atual + direcao * PASSO_ZOOM) * 100) / 100, ZOOM_MIN, ZOOM_MAX);
}

/** Página destino ao navegar, dentro de [1, total] (total desconhecido: sem teto). */
export function paginaDestino(atual: number, delta: number, total: number | null): number {
  const destino = Math.max(1, atual + delta);
  return total === null ? destino : Math.min(destino, total);
}
