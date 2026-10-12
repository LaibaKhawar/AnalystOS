const PAINT_PROPS = [
  'fill',
  'stroke',
  'stroke-width',
  'opacity',
  'fill-opacity',
  'stroke-opacity',
  'font-size',
  'font-family',
  'font-weight',
  'text-anchor',
] as const

/** Clone an on-screen SVG and inline computed paint so CSS variables survive outside the page. */
export function serializeSvg(svg: SVGSVGElement, background: string): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  const source = svg.querySelectorAll('*')
  const target = clone.querySelectorAll('*')
  source.forEach((node, i) => {
    const computed = window.getComputedStyle(node)
    const out = target[i] as SVGElement | undefined
    if (!out) return
    for (const prop of PAINT_PROPS) {
      const value = computed.getPropertyValue(prop)
      if (value) out.setAttribute(prop, value)
    }
  })
  const width = svg.getAttribute('width') ?? String(svg.clientWidth)
  const height = svg.getAttribute('height') ?? String(svg.clientHeight)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', width)
  clone.setAttribute('height', height)
  clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('width', '100%')
  bg.setAttribute('height', '100%')
  bg.setAttribute('fill', background)
  clone.insertBefore(bg, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}

export function svgToPngBlob(svgText: string, width: number, height: number, scale = 2): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' }))
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = width * scale
      canvas.height = height * scale
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        URL.revokeObjectURL(url)
        reject(new Error('Canvas is not available in this browser.'))
        return
      }
      ctx.scale(scale, scale)
      ctx.drawImage(img, 0, 0, width, height)
      URL.revokeObjectURL(url)
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG export failed.'))), 'image/png')
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not render the chart image.'))
    }
    img.src = url
  })
}

export function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 60) || 'chart'
  )
}
