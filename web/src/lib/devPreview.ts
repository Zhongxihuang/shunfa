export const DEV_PREVIEW_TOKEN = 'dev_mock_token';


export function isDevPreviewToken(token: string | null | undefined): boolean {
  return token === DEV_PREVIEW_TOKEN;
}
