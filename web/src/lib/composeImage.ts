export async function renderPageToPng(el: HTMLElement): Promise<string> {
  await document.fonts.ready;
  const html2canvas = (await import('html2canvas')).default;
  const canvas = await html2canvas(el, {
    scale: 3,
    backgroundColor: null,
    useCORS: true,
    logging: false,
  });
  return canvas.toDataURL('image/png');
}

export async function downloadAsZip(pngs: string[], filename: string): Promise<void> {
  const JSZip = (await import('jszip')).default;
  const zip = new JSZip();
  pngs.forEach((dataUrl, i) => {
    const base64 = dataUrl.replace(/^data:image\/png;base64,/, '');
    zip.file(`${filename}-${i + 1}.png`, base64, { base64: true });
  });
  const blob = await zip.generateAsync({ type: 'blob' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadSinglePng(dataUrl: string, filename: string): void {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = `${filename}.png`;
  a.click();
}
