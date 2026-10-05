import { deflateSync } from "node:zlib";
const W = 320,
  H = 160,
  S = 44;
export function randomInt(min, max) {
  const limit = Math.floor(4294967296 / (max - min + 1)) * (max - min + 1);
  let n;
  do {
    n = crypto.getRandomValues(new Uint32Array(1))[0];
  } while (n >= limit);
  return min + (n % (max - min + 1));
}
const crcTable = Array.from({ length: 256 }, (_, n) => {
  for (let k = 0; k < 8; k++) n = n & 1 ? 0xedb88320 ^ (n >>> 1) : n >>> 1;
  return n >>> 0;
});
function crc(a) {
  let c = 0xffffffff;
  for (const b of a) c = crcTable[(c ^ b) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(name, data) {
  const b = Buffer.alloc(data.length + 12);
  b.writeUInt32BE(data.length);
  b.write(name, 4);
  Buffer.from(data).copy(b, 8);
  b.writeUInt32BE(crc(b.subarray(4, -4)), b.length - 4);
  return b;
}
export function png(w, h, data) {
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++)
    Buffer.from(data.subarray(y * w * 4, (y + 1) * w * 4)).copy(
      raw,
      y * (w * 4 + 1) + 1,
    );
  const head = Buffer.alloc(13);
  head.writeUInt32BE(w);
  head.writeUInt32BE(h, 4);
  head[8] = 8;
  head[9] = 6;
  return (
    "data:image/png;base64," +
    Buffer.concat([
      Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
      chunk("IHDR", head),
      chunk("IDAT", deflateSync(raw)),
      chunk("IEND", Buffer.alloc(0)),
    ]).toString("base64")
  );
}
function mask(x, y) {
  const circle = (a, b, r) => (x - a) ** 2 + (y - b) ** 2 < r * r;
  return (
    ((x >= 6 && x < 38 && y >= 6 && y < 38) ||
      circle(22, 6, 6) ||
      circle(38, 22, 6)) &&
    !circle(6, 22, 6) &&
    !circle(22, 38, 6)
  );
}
export function makePuzzle(
  answer = randomInt(78, 264),
  py = randomInt(42, 105),
) {
  const data = new Uint8Array(W * H * 4),
    piece = new Uint8Array(S * S * 4),
    noiseBytes = crypto.getRandomValues(new Uint8Array(W * H));
  const phase = randomInt(0, 100) / 13,
    sun = randomInt(28, 290);
  const palettes = [
    [
      [155, 202, 217],
      [206, 222, 204],
      [99, 153, 151],
      [44, 112, 115],
      [21, 75, 86],
    ],
    [
      [204, 181, 158],
      [230, 210, 169],
      [151, 153, 133],
      [81, 119, 107],
      [39, 77, 77],
    ],
    [
      [164, 186, 220],
      [223, 211, 215],
      [119, 136, 178],
      [74, 106, 153],
      [41, 66, 115],
    ],
  ];
  const palette = palettes[randomInt(0, 2)];
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++) {
      let color = palette[0].map((c, i) =>
        Math.round(c + ((palette[1][i] - c) * y) / H),
      );
      if ((x - sun) ** 2 + (y - 36) ** 2 < 150) color = [249, 234, 188];
      for (let layer = 0; layer < 3; layer++) {
        const horizon =
          77 +
          layer * 24 +
          Math.sin(x / (35 - layer * 7) + phase + layer) * 17 +
          Math.sin(x / 14 + phase) * 4;
        if (y > horizon) color = palette[layer + 2];
      }
      const noise = (noiseBytes[y * W + x] % 15) - 7;
      const p = (y * W + x) * 4;
      for (let c = 0; c < 3; c++)
        data[p + c] = Math.max(0, Math.min(255, color[c] + noise));
      data[p + 3] = 255;
    }
  for (let y = 0; y < S; y++)
    for (let x = 0; x < S; x++) {
      if (!mask(x, y)) continue;
      const p = (y * S + x) * 4,
        q = ((py + y) * W + answer + x) * 4;
      const edge =
        !mask(x - 1, y) ||
        !mask(x + 1, y) ||
        !mask(x, y - 1) ||
        !mask(x, y + 1);
      for (let c = 0; c < 3; c++) {
        piece[p + c] = edge ? 250 : data[q + c];
        data[q + c] = edge ? 235 : Math.round(data[q + c] * 0.32);
      }
      piece[p + 3] = 255;
    }
  return {
    answer,
    pieceY: py,
    background: png(W, H, data),
    piece: png(S, S, piece),
    width: W,
    height: H,
    pieceWidth: S,
  };
}
