// Número único do CNJ (Resolução 65/2008): NNNNNNN-DD.AAAA.J.TR.OOOO, dígito pelo módulo 97.
// Mesma regra de src/lupa/dominio/cnj.py; o servidor reconfere.

const PADRAO = /^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$/;

export function digitoVerificador(
  sequencial: string,
  ano: string,
  justica: string,
  tribunal: string,
  origem: string,
): string {
  const base = BigInt(`${sequencial}${ano}${justica}${tribunal}${origem}00`);
  return String(98n - (base % 97n)).padStart(2, '0');
}

/** Mensagem de erro, ou string vazia quando o número é válido. */
export function problemaCnj(numero: string): string {
  const partes = PADRAO.exec(numero.trim());
  if (!partes) return 'Use o formato NNNNNNN-DD.AAAA.J.TR.OOOO.';
  const [, sequencial, digito, ano, justica, tribunal, origem] = partes as unknown as string[];
  const esperado = digitoVerificador(
    sequencial ?? '',
    ano ?? '',
    justica ?? '',
    tribunal ?? '',
    origem ?? '',
  );
  return esperado === digito ? '' : 'Dígito verificador não confere.';
}

/** Aplica a máscara enquanto a pessoa digita (só algarismos contam). */
export function mascararCnj(texto: string): string {
  const d = texto.replace(/\D/g, '').slice(0, 20);
  const cortes: [number, string][] = [
    [7, '-'],
    [9, '.'],
    [13, '.'],
    [14, '.'],
    [16, '.'],
  ];
  let saida = '';
  for (let i = 0; i < d.length; i++) {
    const corte = cortes.find(([posicao]) => posicao === i);
    if (corte) saida += corte[1];
    saida += d[i];
  }
  return saida;
}
