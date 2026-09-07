/** Uncompressed ZIP32 for already-compressed images; no new runtime dependency. */
export function zipDeImagens(files: { name: string; data: Uint8Array }[]): Blob {
  if (!files.length || files.length > 45) throw Error('Selecione de 1 a 45 arquivos.');
  const entries = new Set<string>(); const parts: ArrayBuffer[] = []; const central: ArrayBuffer[] = [];
  let offset = 0; let total = 0;
  const crc32 = (data: Uint8Array) => {
    let crc = 0xffffffff;
    for (const byte of data) { crc ^= byte; for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); }
    return (crc ^ 0xffffffff) >>> 0;
  };
  for (const file of files) {
    if (!/^[a-zA-Z0-9_-]+\.(png|jpg|webp)$/.test(file.name) || entries.has(file.name)) throw Error('Nome de arquivo inválido ou repetido.');
    entries.add(file.name); total += file.data.byteLength;
    if (total > 100 * 1024 * 1024) throw Error('O ZIP excede 100 MB.');
    const name = new TextEncoder().encode(file.name); const crc = crc32(file.data);
    const local = new ArrayBuffer(30 + name.length); const l = new DataView(local);
    l.setUint32(0, 0x04034b50, true); l.setUint16(4, 20, true); l.setUint16(6, 0x800, true);
    l.setUint16(12, 33, true); l.setUint32(14, crc, true); l.setUint32(18, file.data.length, true); l.setUint32(22, file.data.length, true); l.setUint16(26, name.length, true);
    new Uint8Array(local).set(name, 30);
    const directory = new ArrayBuffer(46 + name.length); const d = new DataView(directory);
    d.setUint32(0, 0x02014b50, true); d.setUint16(4, 20, true); d.setUint16(6, 20, true); d.setUint16(8, 0x800, true); d.setUint16(14, 33, true);
    d.setUint32(16, crc, true); d.setUint32(20, file.data.length, true); d.setUint32(24, file.data.length, true); d.setUint16(28, name.length, true); d.setUint32(42, offset, true);
    new Uint8Array(directory).set(name, 46);
    const bytes = new ArrayBuffer(file.data.length); new Uint8Array(bytes).set(file.data);
    parts.push(local, bytes); central.push(directory); offset += local.byteLength + bytes.byteLength;
  }
  const end = new ArrayBuffer(22); const e = new DataView(end);
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true);
  e.setUint32(12, central.reduce((n, b) => n + b.byteLength, 0), true); e.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end], { type: 'application/zip' });
}
