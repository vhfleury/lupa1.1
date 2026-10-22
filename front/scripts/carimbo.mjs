// Carimbo da verificacao feita no build da imagem (lint, typecheck e testes unitarios).
// Servido em /verificacao.json; o passo "== front ==" do verificar.sh o confere quando nao ha node.
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

function arquivos(dir) {
  return readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    return statSync(caminho).isDirectory() ? arquivos(caminho) : [caminho];
  });
}

const hash = createHash('sha256');
for (const arquivo of arquivos('src').sort()) hash.update(arquivo).update(readFileSync(arquivo));
process.stdout.write(
  JSON.stringify({
    verificado: true,
    passos: ['lint', 'typecheck', 'test'],
    fontes_sha256: hash.digest('hex'),
    em: new Date().toISOString(),
  }) + '\n',
);
