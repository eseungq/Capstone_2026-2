import { adaptInspectionDetailResponseV4 } from './adapter';
import type { ApiV4ErrorEnvelope, InspectionViewV4 } from './types';

export class BackendV4HttpError extends Error {
  constructor(public status: number, public code: string, message: string, public traceId: string | null) {
    super(message);
    this.name = 'BackendV4HttpError';
  }
}

export interface InspectionFetchOptions {
  baseUrl: string;       // 예: http://192.168.x.x:8080/api/v1 (실제 Mac IP만 개발 환경에서 입력)
  accessToken: string;   // 로그인 성공 후 보유한 JWT. 코드에 하드코딩하지 말 것.
  inspectionId: string;  // INS-000006이 아닌 UUID
  signal?: AbortSignal;
  fetchImpl?: typeof fetch; // 테스트 주입용
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * 실제 서버가 실행 중일 때만 호출하세요. 이 모듈만 추가해도 기존 Mock 화면은 API를 호출하지 않습니다.
 * 토큰 만료 시 자동 재발급은 별도 단계(로그인/인증 모듈)에서 처리합니다.
 */
export async function fetchInspectionDetailV4(opts: InspectionFetchOptions): Promise<InspectionViewV4> {
  if (!opts.baseUrl || !/^https?:\/\//i.test(opts.baseUrl)) throw new Error('API 기본 주소가 설정되지 않았습니다.');
  if (!opts.accessToken) throw new Error('Access Token이 없습니다. 로그인 연결 후 사용하세요.');
  if (!UUID.test(opts.inspectionId)) throw new Error('API 호출에는 inspectionNo 대신 UUID inspectionId가 필요합니다.');

  const base = opts.baseUrl.replace(/\/+$/, '');
  const fetcher = opts.fetchImpl ?? fetch;
  const res = await fetcher(`${base}/inspections/${encodeURIComponent(opts.inspectionId)}`, {
    method: 'GET',
    headers: { Accept: 'application/json', Authorization: `Bearer ${opts.accessToken}` },
    signal: opts.signal,
  });

  let json: unknown;
  try { json = await res.json(); }
  catch { throw new BackendV4HttpError(res.status, 'INVALID_JSON', '서버 JSON 응답을 읽지 못했습니다.', null); }

  if (!res.ok) {
    const body = json as Partial<ApiV4ErrorEnvelope> | null;
    const err = body && typeof body === 'object' ? body.error : undefined;
    throw new BackendV4HttpError(
      res.status,
      typeof err?.code === 'string' ? err.code : 'UNKNOWN',
      typeof err?.message === 'string' ? err.message : `서버 오류 (${res.status})`,
      typeof err?.traceId === 'string' ? err.traceId : null,
    );
  }
  return adaptInspectionDetailResponseV4(json);
}
