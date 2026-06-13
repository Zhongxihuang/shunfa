export const DEV_PREVIEW_TOKEN = process.env.NODE_ENV === 'development' ? 'dev_mock_token' : '';

export function isDevPreviewToken(token: string | null | undefined): boolean {
  if (process.env.NODE_ENV !== 'development') return false;
  return token === 'dev_mock_token';
}
