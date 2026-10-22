// Fixture global (6.10): começa cada execução com o diretório de estado compartilhado vazio. Nele
// os arquivos de teste guardam as contas que criaram (senha nova e segredo TOTP, só em /tmp do
// contêiner efêmero do E2E) e o estado de sessão do navegador, para os testes finais (acessibilidade,
// segurança, auditoria como admin) entrarem sem refazer o primeiro acesso.
import { mkdirSync, rmSync } from 'node:fs';
import { DIRETORIO_ESTADO } from './credenciais';

export default function preparar(): void {
  rmSync(DIRETORIO_ESTADO, { recursive: true, force: true });
  mkdirSync(DIRETORIO_ESTADO, { recursive: true, mode: 0o700 });
}
