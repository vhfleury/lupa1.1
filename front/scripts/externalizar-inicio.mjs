// Etapa 6.10: a CSP do proxy proíbe script e estilo inline (`script-src 'self'`, `style-src
// 'self'`). O SvelteKit grava no index.html um <script> inline que dá a partida na SPA; aqui ele
// vira o arquivo /inicio.js (mesmo origin), precedido da aplicação do tema salvo, para não piscar
// o tema errado. Depois confere que não sobrou nenhum script, estilo ou atributo de evento inline.
import { readFileSync, writeFileSync } from 'node:fs';

const INDICE = 'build/index.html';
const DESTINO = 'build/inicio.js';
const TEMA = `try {
  var tema = window.localStorage.getItem('lupa.tema');
  if (tema === 'claro' || tema === 'escuro') document.documentElement.dataset.tema = tema;
} catch (e) {
  // Sem localStorage (modo privado ou bloqueado): segue o tema do sistema.
}
`;

let html = readFileSync(INDICE, 'utf8');
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (inline.length !== 1) throw new Error(`esperado 1 script inline no index.html, achei ${inline.length}`);
const [bloco, codigo] = inline[0];
writeFileSync(DESTINO, `${TEMA}${codigo.trim()}\n`);
html = html.replace(bloco, '<script src="/inicio.js"></script>');

const proibidos = [
  [/<script(?![^>]*\bsrc=)[^>]*>/i, 'script inline'],
  [/<style[\s>]/i, 'bloco <style>'],
  [/\sstyle=/i, 'atributo style'],
  [/\son[a-z]+=/i, 'atributo de evento'],
];
for (const [padrao, nome] of proibidos) {
  if (padrao.test(html)) throw new Error(`index.html ainda tem ${nome}; a CSP vai bloquear`);
}
writeFileSync(INDICE, html);
process.stdout.write('inicio.js externalizado; index.html sem conteúdo inline\n');
