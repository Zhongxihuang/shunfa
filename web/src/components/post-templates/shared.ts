export const TEMPLATE_WIDTH = 414;   // CSS px, html2canvas scale:3 → 1242px
export const TEMPLATE_HEIGHT = 552;  // CSS px, html2canvas scale:3 → 1656px

export interface PostTemplateProps {
  pageText: string;
  pageIndex: number;    // 0-based
  totalPages: number;
}

export function getAdaptiveTextStyle(text: string, baseSize = 28) {
  const length = text.replace(/\s/g, '').length;
  // Thresholds tuned for 3-layer analysis cards (per-page budget: 80-160 chars).
  if (length > 155) return { fontSize: baseSize - 8, lineHeight: 1.56 };
  if (length > 120) return { fontSize: baseSize - 5, lineHeight: 1.62 };
  if (length > 80) return { fontSize: baseSize - 2, lineHeight: 1.7 };
  return { fontSize: baseSize, lineHeight: 1.78 };
}

export function normalizeTemplateText(text: string) {
  return text
    .replace(/\*\*/g, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/`/g, '')
    .trim();
}

export function splitLead(text: string): { lead: string; rest: string } {
  const trimmed = text.trim();
  const punctuationIndex = trimmed.search(/[。！？!?；;]/);
  if (punctuationIndex > 8 && punctuationIndex < 34) {
    return {
      lead: trimmed.slice(0, punctuationIndex + 1),
      rest: trimmed.slice(punctuationIndex + 1).trim(),
    };
  }
  if (trimmed.length > 30) {
    return {
      lead: `${trimmed.slice(0, 24)}…`,
      rest: trimmed.slice(24).trim(),
    };
  }
  return { lead: trimmed, rest: '' };
}
