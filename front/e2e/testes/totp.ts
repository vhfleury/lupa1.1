// TOTP (RFC 6238, SHA-1, 6 dígitos, 30 s), o mesmo que o aplicativo autenticador calcularia
// a partir do segredo exibido na tela. Sem e-mail, sem atalho no banco.
import { createHmac } from 'node:crypto';

const ALFABETO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const PERIODO = 30;

function base32(texto: string): Buffer {
  const limpo = texto.replace(/=+$/, '').toUpperCase();
  let bits = '';
  for (const caractere of limpo) {
    const valor = ALFABETO.indexOf(caractere);
    if (valor < 0) throw new Error('segredo base32 inválido');
    bits += valor.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

export function codigoTotp(segredo: string, passo: number): string {
  const contador = Buffer.alloc(8);
  contador.writeBigUInt64BE(BigInt(passo));
  const hmac = createHmac('sha1', base32(segredo)).update(contador).digest();
  const deslocamento = (hmac[hmac.length - 1] ?? 0) & 0x0f;
  const numero = hmac.readUInt32BE(deslocamento) & 0x7fffffff;
  return String(numero % 1_000_000).padStart(6, '0');
}

export function passoAtual(): number {
  return Math.floor(Date.now() / 1000 / PERIODO);
}

/** Segredo lido da URI otpauth:// exibida na tela. */
export function segredoDaUri(uri: string): string {
  const url = new URL(uri);
  if (url.protocol !== 'otpauth:') throw new Error('URI não é otpauth://');
  const segredo = url.searchParams.get('secret');
  if (!segredo) throw new Error('URI sem segredo');
  return segredo;
}

/** Autenticador que nunca repete passo (o servidor recusa código de passo já usado). */
export class Autenticador {
  private ultimo: number;

  /** `ultimo`: último passo já usado (6.10: a conta é compartilhada entre arquivos de teste). */
  constructor(
    readonly segredo: string,
    ultimo = -1,
  ) {
    this.ultimo = ultimo;
  }

  get ultimoPasso(): number {
    return this.ultimo;
  }

  async proximo(): Promise<string> {
    for (;;) {
      const atual = passoAtual();
      const passo = Math.max(atual, this.ultimo + 1);
      // 6.10: só o passo corrente (nunca o seguinte): sem depender da tolerância de relógio.
      if (passo <= atual) {
        this.ultimo = passo;
        return codigoTotp(this.segredo, passo);
      }
      await new Promise((resolver) => setTimeout(resolver, 1000));
    }
  }

  /** Código certamente errado (de um passo distante), para testar a recusa. */
  errado(): string {
    return codigoTotp(this.segredo, passoAtual() + 50);
  }
}
