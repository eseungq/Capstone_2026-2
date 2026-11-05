/**
 * API v4 공통 HTTP 처리 — 서버 연동 전 준비 모듈.
 * 2026-10-28 필드 대조표: {data} 성공 / {error:{code,message,traceId}} 오류.
 * 실제 서버 주소와 토큰은 소스에 하드코딩하지 않습니다.
 */
export type ApiFetch = (input: string, init?: RequestInit) => Promise<Response>;
export type BodyMode = 'data' | 'empty';

export class ApiV4RequestError extends Error {
  constructor(
    public readonly httpStatus: number,
    public readonly code: string,
    message: string,
    public readonly traceId: string | null,
  ) {
    super(message);
    this.name = 'ApiV4RequestError';
  }
}

export interface ApiV4Request {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string; // /api/v1 뒤에 이어 붙일 상대 경로 (예: /inspections)
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
  mode?: BodyMode;
  fetchImpl?: ApiFetch;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function unwrapApiV4Data<T>(response: unknown): T {
  if (!isRecord(response) || !Object.prototype.hasOwnProperty.call(response, 'data')) {
    throw new ApiV4RequestError(200, 'INVALID_ENVELOPE', '서버 성공 응답에 data 필드가 없습니다.', null);
  }
  return response.data as T; // 개별 데이터 스키마 검증은 호출부에서 수행
}

export function parseApiV4Error(
  httpStatus: number,
  response: unknown,
  headerTraceId: string | null = null,
): ApiV4RequestError {
  const e = isRecord(response) && isRecord(response.error) ? response.error : null;
  return new ApiV4RequestError(
    httpStatus,
    typeof e?.code === 'string' ? e.code : 'HTTP_ERROR',
    typeof e?.message === 'string' ? e.message : `서버 요청 실패 (HTTP ${httpStatus})`,
    typeof e?.traceId === 'string' ? e.traceId : headerTraceId,
  );
}

/** mode='empty': POST /retry 같은 정상 202 빈 본문 처리. */
export async function requestApiV4<T>(
  baseUrl: string,
  options: ApiV4Request,
): Promise<T> {
  if (!/^https?:\/\//i.test(baseUrl) || !baseUrl.trim()) {
    throw new Error('baseUrl에 http(s)://호스트/api/v1 형식의 주소를 설정해야 합니다.');
  }
  if (!options.path.startsWith('/') || options.path.startsWith('//')) {
    throw new Error('API path는 /로 시작하는 상대 경로여야 합니다.');
  }
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  const fetcher = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetcher(`${baseUrl.replace(/\/+$/, '')}${options.path}`, {
      method,
      headers,
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') throw err;
    throw new ApiV4RequestError(0, 'NETWORK_ERROR', '서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.', null);
  }

  const traceHeader = response.headers?.get('X-Trace-Id') ?? null;
  let parsed: unknown;
  try {
    const raw = await response.text();
    parsed = raw.length > 0 ? JSON.parse(raw) : undefined;
  } catch {
    throw new ApiV4RequestError(response.status, 'INVALID_JSON', '서버 응답을 JSON으로 읽지 못했습니다.', traceHeader);
  }
  if (!response.ok) throw parseApiV4Error(response.status, parsed, traceHeader);
  if ((options.mode ?? 'data') === 'empty') return undefined as T;
  try {
    return unwrapApiV4Data<T>(parsed);
  } catch (err) {
    if (err instanceof ApiV4RequestError) {
      throw new ApiV4RequestError(response.status, err.code, err.message, traceHeader);
    }
    throw err;
  }
}
