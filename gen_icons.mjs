/**
 * gen_icons.mjs
 * Generate all Tauri icon sizes from logo.svg using @resvg/resvg-js.
 * Run: node gen_icons.mjs
 */
import { Resvg } from '@resvg/resvg-js';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const SVG_PATH  = join(__dirname, 'View/public/logo.svg');
const ICONS_DIR = join(__dirname, 'exe/src-tauri/icons');

const svgData = readFileSync(SVG_PATH, 'utf8');

function renderPng(size) {
  const resvg = new Resvg(svgData, {
    fitTo: { mode: 'width', value: size },
    background: 'transparent',
  });
  const pngData = resvg.render();
  return pngData.asPng();
}

mkdirSync(ICONS_DIR, { recursive: true });

const sizes = [
  { file: '32x32.png',          px: 32  },
  { file: '128x128.png',        px: 128 },
  { file: '128x128@2x.png',     px: 256 },
  { file: 'icon.png',           px: 512 },
  { file: 'Square30x30Logo.png', px: 30 },
  { file: 'Square44x44Logo.png', px: 44 },
  { file: 'Square71x71Logo.png', px: 71 },
  { file: 'Square89x89Logo.png', px: 89 },
  { file: 'Square107x107Logo.png', px: 107 },
  { file: 'Square142x142Logo.png', px: 142 },
  { file: 'Square150x150Logo.png', px: 150 },
  { file: 'Square284x284Logo.png', px: 284 },
  { file: 'Square310x310Logo.png', px: 310 },
  { file: 'StoreLogo.png',       px: 50  },
];

for (const { file, px } of sizes) {
  const png = renderPng(px);
  writeFileSync(join(ICONS_DIR, file), png);
  console.log(`✓ ${file} (${px}×${px})`);
}

// ── ICO (multi-size: 16, 32, 48, 256) ────────────────────────────────────────
// Build a minimal ICO file manually from PNG frames.
function buildIco(frames) {
  // frames: [{ png: Buffer, size: number }, ...]
  const HEADER = 6;
  const DIRENTRY = 16;
  const headerBuf = Buffer.alloc(HEADER);
  headerBuf.writeUInt16LE(0, 0);              // reserved
  headerBuf.writeUInt16LE(1, 2);              // type: ICO
  headerBuf.writeUInt16LE(frames.length, 4);  // count

  let offset = HEADER + DIRENTRY * frames.length;
  const dirs = [];
  for (const f of frames) {
    const dir = Buffer.alloc(DIRENTRY);
    const dim = f.size >= 256 ? 0 : f.size;   // 0 = 256 per ICO spec
    dir.writeUInt8(dim, 0);                    // width
    dir.writeUInt8(dim, 1);                    // height
    dir.writeUInt8(0, 2);                      // color count
    dir.writeUInt8(0, 3);                      // reserved
    dir.writeUInt16LE(1, 4);                   // planes
    dir.writeUInt16LE(32, 6);                  // bit count
    dir.writeUInt32LE(f.png.length, 8);        // size
    dir.writeUInt32LE(offset, 12);             // offset
    dirs.push(dir);
    offset += f.png.length;
  }

  return Buffer.concat([headerBuf, ...dirs, ...frames.map(f => f.png)]);
}

const icoSizes = [16, 32, 48, 256];
const icoFrames = icoSizes.map(px => ({ png: renderPng(px), size: px }));
const icoBuf = buildIco(icoFrames);
writeFileSync(join(ICONS_DIR, 'icon.ico'), icoBuf);
console.log('✓ icon.ico (16, 32, 48, 256)');

// ── ICNS (Apple Icon Image format) ───────────────────────────────────────────
// Build a minimal ICNS with ic07 (128) and ic13 (128@2x/256) entries.
function buildIcns(entries) {
  // entries: [{ type: string (4 chars), png: Buffer }, ...]
  const header = Buffer.alloc(8);
  let totalSize = 8;
  for (const e of entries) totalSize += 8 + e.png.length;
  header.write('icns', 0, 'ascii');
  header.writeUInt32BE(totalSize, 4);

  const parts = [header];
  for (const e of entries) {
    const entryHeader = Buffer.alloc(8);
    entryHeader.write(e.type, 0, 'ascii');
    entryHeader.writeUInt32BE(8 + e.png.length, 4);
    parts.push(entryHeader, e.png);
  }
  return Buffer.concat(parts);
}

const icnsEntries = [
  { type: 'ic07', png: renderPng(128)  },  // 128×128
  { type: 'ic08', png: renderPng(256)  },  // 256×256 (128@2x)
  { type: 'ic09', png: renderPng(512)  },  // 512×512
  { type: 'ic10', png: renderPng(1024) },  // 1024×1024 (512@2x)
];
const icnsBuf = buildIcns(icnsEntries);
writeFileSync(join(ICONS_DIR, 'icon.icns'), icnsBuf);
console.log('✓ icon.icns (128, 256, 512, 1024)');

console.log('\nAll icons generated successfully.');
