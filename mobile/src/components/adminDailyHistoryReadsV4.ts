import type {
  DailyDetailV4,
  DailyHistoryRowV4,
} from '../api/backendV4/adminDailyHistoryCoreV4';
import {DailyQueryInputErrorV4} from '../api/backendV4/adminDailyHistoryCoreV4';
import {ApiV4RequestError} from '../api/backendV4/httpCore';
import type {createDailyHistoryServiceV4} from '../api/backendV4/adminDailyHistoryServiceV4';

export interface DailyReadState<T> {
  value: T | null;
  loading: boolean;
  error: string | null;
}

export const idleDailyRead = {value: null, loading: false, error: null};

function readErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DailyQueryInputErrorV4) return error.message;
  if (error instanceof ApiV4RequestError) {
    if (error.httpStatus === 401) return '로그인이 만료됐습니다. 다시 로그인해 주세요.';
    if (error.httpStatus === 403) return '관리자 계정으로 로그인해 주세요.';
    if (error.code === 'NETWORK_ERROR') return '서버에 연결할 수 없습니다. 네트워크를 확인하고 다시 시도해 주세요.';
  }
  return fallback;
}

function latestRead<T>(publish: (state: DailyReadState<T>) => void, fallback: string) {
  let version = 0;
  return {
    reset() {
      version++;
      publish(idleDailyRead);
    },
    async run(read: () => Promise<T>) {
      const current = ++version;
      publish({value: null, loading: true, error: null});
      try {
        const value = await read();
        if (version === current) publish({value, loading: false, error: null});
      } catch (error) {
        if (version === current) {
          publish({value: null, loading: false, error: readErrorMessage(error, fallback)});
        }
      }
    },
  };
}

export function createDailyHistoryReadsV4(
  service: ReturnType<typeof createDailyHistoryServiceV4>,
  publishRows: (state: DailyReadState<DailyHistoryRowV4[]>) => void,
  publishDetail: (state: DailyReadState<DailyDetailV4>) => void,
) {
  const rows = latestRead(publishRows, '통계를 불러오지 못했습니다. 잠시 후 다시 조회해 주세요.');
  const detail = latestRead(publishDetail, '기준 주변의 검사를 불러오지 못했습니다. 잠시 후 다시 조회해 주세요.');
  return {
    reset() {
      rows.reset();
      detail.reset();
    },
    resetDetail: detail.reset,
    loadRows(part: string, from: string, to: string) {
      detail.reset();
      return rows.run(() => service.daily(part, from, to));
    },
    loadDetail(part: string, date: string, policyId: string, band: string) {
      return detail.run(() => service.detail(part, date, policyId, band));
    },
  };
}
