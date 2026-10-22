// Guarda de rotas da SPA. Roda no navegador a cada navegação: confere a sessão no servidor,
// manda para o login quando não há sessão e para a troca de senha quando ela é obrigatória.
import { redirect } from '@sveltejs/kit';
import { consumirMarcador } from '$lib/marcador';
import { carregarSessao, sessao } from '$lib/sessao.svelte';
import type { LayoutLoad } from './$types';

export const ssr = false;
export const prerender = false;
export const trailingSlash = 'never';

const LOGIN = '/login';
const TROCAR_SENHA = '/trocar-senha';

export const load: LayoutLoad = async ({ url, fetch }) => {
  const anterior = sessao.atual;
  const atual = await carregarSessao(fetch);
  // 6.10: numa recarga completa a memória some; o marcador em sessionStorage diz se havia
  // sessão neste separador, para avisar "sessão encerrada ou expirada".
  const expirou = atual === null && (consumirMarcador() || anterior !== null);
  if (url.pathname === LOGIN) {
    if (atual && !atual.troca_senha_obrigatoria) redirect(307, '/');
    if (expirou && url.searchParams.get('motivo') !== 'expirada') {
      redirect(307, `${LOGIN}?motivo=expirada`);
    }
    return {};
  }
  if (atual === null) redirect(307, expirou ? `${LOGIN}?motivo=expirada` : LOGIN);
  if (atual.troca_senha_obrigatoria && url.pathname !== TROCAR_SENHA) redirect(307, TROCAR_SENHA);
  return {};
};
