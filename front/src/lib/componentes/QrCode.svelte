<script lang="ts">
  // Desenha o QR code no cliente a partir da URI otpauth:// (nenhum HTML vindo de fora).
  import QRCode from 'qrcode';

  interface Props {
    texto: string;
    rotulo: string;
    tamanho?: number;
  }

  let { texto, rotulo, tamanho = 220 }: Props = $props();

  const MARGEM = 4;

  const desenho = $derived.by(() => {
    const matriz = QRCode.create(texto, { errorCorrectionLevel: 'M' }).modules;
    let caminho = '';
    for (let linha = 0; linha < matriz.size; linha++) {
      for (let coluna = 0; coluna < matriz.size; coluna++) {
        if (matriz.get(linha, coluna)) caminho += `M${coluna + MARGEM},${linha + MARGEM}h1v1h-1z`;
      }
    }
    return { lado: matriz.size + 2 * MARGEM, caminho };
  });
</script>

<svg
  role="img"
  aria-label={rotulo}
  width={tamanho}
  height={tamanho}
  viewBox="0 0 {desenho.lado} {desenho.lado}"
  shape-rendering="crispEdges"
  data-testid="qr-code"
>
  <rect width={desenho.lado} height={desenho.lado} fill="#ffffff" />
  <path d={desenho.caminho} fill="#000000" />
</svg>
