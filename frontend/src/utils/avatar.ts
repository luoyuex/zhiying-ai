const MAX_SOURCE_BYTES = 8 * 1024 * 1024
const TARGET_SIZE = 256

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('图片读取失败'))
    }
    image.src = url
  })
}

/** 居中裁剪并压缩为 256×256 JPEG data URL，避免上传大图。 */
export async function fileToAvatarDataUrl(file: File): Promise<string> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    throw new Error('仅支持 JPG、PNG 或 WebP 图片')
  }
  if (file.size > MAX_SOURCE_BYTES) {
    throw new Error('图片不能超过 8 MB')
  }

  const image = await loadImage(file)
  const side = Math.min(image.naturalWidth, image.naturalHeight)
  if (!side) throw new Error('图片内容无效')
  const sx = (image.naturalWidth - side) / 2
  const sy = (image.naturalHeight - side) / 2

  const canvas = document.createElement('canvas')
  canvas.width = TARGET_SIZE
  canvas.height = TARGET_SIZE
  const context = canvas.getContext('2d')
  if (!context) throw new Error('当前浏览器不支持图片处理')
  context.imageSmoothingQuality = 'high'
  context.drawImage(image, sx, sy, side, side, 0, 0, TARGET_SIZE, TARGET_SIZE)
  return canvas.toDataURL('image/jpeg', 0.86)
}
