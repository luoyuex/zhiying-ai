const MARGIN_MM = 10

/**
 * 把 DOM 节点导出为 A4 PDF。
 * 节点内带 data-pdf-hide 的元素（按钮、提示等）会在截图时临时隐藏。
 */
export async function exportElementToPdf(
  element: HTMLElement,
  filename: string,
): Promise<void> {
  const hidden: { node: HTMLElement; display: string }[] = []
  element.querySelectorAll<HTMLElement>('[data-pdf-hide]').forEach((node) => {
    hidden.push({ node, display: node.style.display })
    node.style.display = 'none'
  })

  try {
    const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
      import('html2canvas-pro'),
      import('jspdf'),
    ])
    await document.fonts.ready
    const canvas = await html2canvas(element, {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true,
      logging: false,
      windowWidth: element.scrollWidth,
    })
    if (!canvas.width || !canvas.height) {
      throw new Error('报告内容为空，无法导出')
    }

    const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()
    const contentWidth = pageWidth - MARGIN_MM * 2
    const contentHeight = pageHeight - MARGIN_MM * 2
    const imageHeight = (canvas.height * contentWidth) / canvas.width
    const imageData = canvas.toDataURL('image/jpeg', 0.95)

    let offset = 0
    while (offset < imageHeight) {
      pdf.addImage(
        imageData,
        'JPEG',
        MARGIN_MM,
        MARGIN_MM - offset,
        contentWidth,
        imageHeight,
        undefined,
        'FAST',
      )
      offset += contentHeight
      if (offset < imageHeight) pdf.addPage()
    }

    pdf.save(filename)
  } finally {
    hidden.forEach(({ node, display }) => {
      node.style.display = display
    })
  }
}

export function pdfFilename(name: string, symbol: string, createdAt: string): string {
  const date = new Date(createdAt)
  const stamp = Number.isNaN(date.getTime())
    ? 'report'
    : `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(
        date.getDate(),
      ).padStart(2, '0')}`
  const safeName = name.replace(/[\\/:*?"<>|]/g, '').trim() || symbol
  return `智盈AI_${safeName}_${symbol}_${stamp}.pdf`
}
