import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')

function crc32(buffer) {
  let crc = 0xffffffff
  for (const byte of buffer) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const typeBuffer = Buffer.from(type)
  const output = Buffer.alloc(data.length + 12)
  output.writeUInt32BE(data.length, 0)
  typeBuffer.copy(output, 4)
  data.copy(output, 8)
  output.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), data.length + 8)
  return output
}

function makeIcon(size) {
  const navy = [0x00, 0x29, 0x70, 0xff]
  const cyan = [0x00, 0xba, 0xf2, 0xff]
  const rows = []
  const stroke = Math.max(10, Math.round(size * 0.13))
  const left = Math.round(size * 0.27)
  const right = Math.round(size * 0.73) - stroke
  const top = Math.round(size * 0.24)
  const bottom = Math.round(size * 0.76)
  const middleTop = Math.round(size * 0.44)
  const middleBottom = Math.round(size * 0.56)

  for (let y = 0; y < size; y += 1) {
    const row = Buffer.alloc(1 + size * 4)
    for (let x = 0; x < size; x += 1) {
      const h = y >= top && y < bottom && (
        (x >= left && x < left + stroke) ||
        (x >= right && x < right + stroke) ||
        (y >= middleTop && y < middleBottom && x >= left && x < right + stroke)
      )
      const color = h ? cyan : navy
      for (let channel = 0; channel < 4; channel += 1) row[1 + x * 4 + channel] = color[channel]
    }
    rows.push(row)
  }

  const header = Buffer.alloc(13)
  header.writeUInt32BE(size, 0)
  header.writeUInt32BE(size, 4)
  header[8] = 8
  header[9] = 6
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(rows), { level: 9 })),
    chunk('IEND', Buffer.alloc(0))
  ])
}

for (const size of [192, 512]) writeFileSync(join(root, `icon-${size}.png`), makeIcon(size))
