/** Limit failed-image URL renewals without disabling healthy expiry refreshes. */
export const MAX_AUTOMATIC_IMAGE_ERROR_REFRESHES_V4 = 2;
export function createImageErrorRefreshBudgetV4() {
  let used = 0;
  return {
    take() {
      if (used >= MAX_AUTOMATIC_IMAGE_ERROR_REFRESHES_V4) return false;
      used++;
      return true;
    },
    reset() { used = 0; },
    exhausted() { return used >= MAX_AUTOMATIC_IMAGE_ERROR_REFRESHES_V4; },
  };
}

/** A server returning near-expired URLs repeatedly must not create a tight GET loop. */
export function imageExpiryRefreshDelayV4(expiryMs: number, lastAttemptMs: number | null, nowMs: number) {
  return Math.max(0, expiryMs - nowMs - 30_000,
    lastAttemptMs === null ? 0 : lastAttemptMs + 30_000 - nowMs);
}
