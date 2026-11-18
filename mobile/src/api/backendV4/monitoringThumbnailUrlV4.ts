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


/** Server's exp is a Unix timestamp (seconds). Signed URLs usually rotate every poll. */
function signedThumbnailExpiryMsV4(uri: string): number | null {
  const match = /[?&]exp=(\d+)(?:[&#]|$)/.exec(uri);
  if (!match) return null;
  const seconds = Number(match[1]);
  return Number.isSafeInteger(seconds) && seconds > 0 ? seconds * 1000 : null;
}

/**
 * A refreshed signature is not a new photo. Keep the loaded image until
 * its signed URL nears expiry, unless the image resource itself changes.
 * Unknown-signature URLs conservatively follow URL changes.
 */
export function monitoringThumbnailNeedsReloadV4(
  currentUrl: string | null,
  incomingUrl: string | null,
  nowMs: number = Date.now(),
): boolean {
  if (!incomingUrl || incomingUrl === currentUrl) return false;
  if (!currentUrl) return true;

  const resource = (uri: string) => uri.split(/[?#]/, 1)[0];
  if (resource(currentUrl) !== resource(incomingUrl)) return true;

  const currentExpiry = signedThumbnailExpiryMsV4(currentUrl);
  if (currentExpiry === null) return true;
  const incomingExpiry = signedThumbnailExpiryMsV4(incomingUrl);
  if (incomingExpiry !== null
    && (incomingExpiry <= currentExpiry || incomingExpiry <= nowMs)) return false;

  // Refresh one minute before expiry. The old photo stays on screen
  // while the hidden image finishes loading, preventing a blank frame.
  return currentExpiry - nowMs <= 60_000;
}
