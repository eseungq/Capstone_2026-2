/**
 * 모니터링 thumbnailUrl은 절대 URL 또는 서버 상대 경로일 수 있습니다.
 * 민감한 서명 쿼리는 수정하지 않고, HTTP(S) 이미지 URL만 RN Image에 전달합니다.
 */
export function resolveMonitoringThumbnailUrlV4(
  value: string | null | undefined,
  baseUrl: string,
): string | null {
  const raw = value?.trim();
  if (!raw || /\s|\\/.test(raw)) return null;
  if (/^https?:\/\/[^/?#]+/i.test(raw)) return raw;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith('//')) return null;

  const base = baseUrl.trim().replace(/\/+$/, '');
  const origin = /^(https?:\/\/[^/]+)/i.exec(base)?.[1] ?? null;
  if (!origin) return null;
  return raw.startsWith('/') ? origin + raw : base + '/' + raw;
}
