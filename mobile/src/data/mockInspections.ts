import { useEffect, useState } from 'react';
import type { ImageSourcePropType } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

// 시연 전용 Mock 데이터입니다. 실제 검사, 실제 AI 예측 또는 검증된 자동 통과 기록이 아닙니다.
// 자동 통과 예시는 운영 상태가 아닌 별도의 MOCK-ONLY 상태로 분리합니다.
export type InspectionStatus = 'REVIEW' | 'FAILED' | 'RECEIVED' | 'ANALYZING' | 'AUTO_PASS_EXAMPLE';
export type AIPrediction = 'GOOD' | 'DEFECT' | null;
export type FinalJudgement = 'PASS' | 'FAIL' | null;
export type Role = 'WORKER' | 'ADMIN';

export type Inspection = {
  id: string;
  partCode: string;
  capturedAt: string;
  status: InspectionStatus;
  originalImage: ImageSourcePropType;
  prediction: AIPrediction;
  calibratedDefectProbability: number | null;
  modelVersion: string | null;
  policyVersion: string | null;
  reviewReason: string | null;
  errorMessage: string | null;
  gradcamAvailable: boolean;
  finalJudgement: FinalJudgement;
  confirmedAt: string | null;
  retryOf: string | null;
  retriedBy: string | null;
};

const door1 = require('../../assets/images/door_inspection_1.png');
const door2 = require('../../assets/images/door_inspection_2.png');

const defaults: Record<string, Inspection> = {
  'INS-006': {
    id: 'INS-006', partCode: 'DOOR', capturedAt: '2026-10-27 14:32',
    status: 'REVIEW', originalImage: door1, prediction: 'DEFECT',
    calibratedDefectProbability: null, modelVersion: 'mock-model-v1',
    policyVersion: null, reviewReason: '작업자의 최종 확인이 필요한 검사입니다 (예시).',
    errorMessage: null, gradcamAvailable: false, finalJudgement: null,
    confirmedAt: null, retryOf: null, retriedBy: null,
  },
  'INS-005': {
    id: 'INS-005', partCode: 'DOOR', capturedAt: '2026-10-27 14:29',
    status: 'REVIEW', originalImage: door2, prediction: 'GOOD',
    calibratedDefectProbability: null, modelVersion: 'mock-model-v1',
    policyVersion: null, reviewReason: '검증된 자동 통과 정책이 없어 확인 대기 중입니다 (예시).',
    errorMessage: null, gradcamAvailable: false, finalJudgement: null,
    confirmedAt: null, retryOf: null, retriedBy: null,
  },
  'INS-007': {
    id: 'INS-007', partCode: 'DOOR', capturedAt: '2026-10-27 14:35',
    status: 'FAILED', originalImage: door2, prediction: null,
    calibratedDefectProbability: null, modelVersion: null,
    policyVersion: null, reviewReason: null,
    errorMessage: 'AI 분석 중 오류가 발생했습니다 (시연용 예시).',
    gradcamAvailable: false, finalJudgement: null,
    confirmedAt: null, retryOf: null, retriedBy: null,
  },
  'INS-008': {
    id: 'INS-008', partCode: 'DOOR', capturedAt: '2026-10-27 14:36',
    status: 'ANALYZING', originalImage: door1, prediction: null,
    calibratedDefectProbability: null, modelVersion: null,
    policyVersion: null, reviewReason: null, errorMessage: null,
    gradcamAvailable: false, finalJudgement: null,
    confirmedAt: null, retryOf: null, retriedBy: null,
  },
  'INS-002': {
    id: 'INS-002', partCode: 'DOOR', capturedAt: '2026-10-27 14:15',
    // 예시용 배지/흐름만 표현. PASS 확정이나 실제 AUTO_PASS 이벤트가 아닙니다.
    status: 'AUTO_PASS_EXAMPLE', originalImage: door1, prediction: 'GOOD',
    calibratedDefectProbability: null, modelVersion: 'mock-model-v1',
    policyVersion: null,
    reviewReason: 'AUTO_PASS 화면 시연 예시입니다. 검증된 정책이 없어 실제 자동 통과가 확정되지 않았습니다.',
    errorMessage: null, gradcamAvailable: false, finalJudgement: null,
    confirmedAt: null, retryOf: null, retriedBy: null,
  },
};

const store: Record<string, Inspection> = Object.fromEntries(
  Object.entries(defaults).map(([id, value]) => [id, { ...value }])
);

// 원본 이미지 자체나 고정된 AI/정책 예시는 저장하지 않습니다.
// 변하는 Mock 판정, 재검사 연결, 접수 시각만 저장합니다.
type PersistedConfirmation = { id: string; judgement: 'PASS' | 'FAIL'; confirmedAt: string };
type PersistedRetry = { id: string; retryOf: string; capturedAt: string };
type PersistedState = { schemaVersion: 1; confirmations: PersistedConfirmation[]; retries: PersistedRetry[] };
const STORAGE_KEY = '@ai-quality-monitor/mock-inspections/v1';
const listeners = new Set<() => void>();
let ready = false;
let revision = 0;
let warning: string | null = null;
let initPromise: Promise<void> | null = null;
let nextRetryNumber = 1000;
let mutationTail: Promise<unknown> = Promise.resolve();

function notify(): void {
  revision += 1;
  listeners.forEach(listener => listener());
}

function snapshot(): PersistedState {
  const values = Object.values(store);
  return {
    schemaVersion: 1,
    confirmations: values
      .filter((item): item is Inspection & { finalJudgement: 'PASS' | 'FAIL'; confirmedAt: string } =>
        item.status === 'REVIEW' && item.finalJudgement !== null && item.confirmedAt !== null)
      .map(item => ({ id: item.id, judgement: item.finalJudgement, confirmedAt: item.confirmedAt })),
    retries: values.filter(item => item.retryOf !== null)
      .map(item => ({ id: item.id, retryOf: item.retryOf!, capturedAt: item.capturedAt })),
  };
}

function makeRetry(original: Inspection, id: string, capturedAt: string): Inspection {
  return {
    id, partCode: original.partCode, capturedAt, status: 'RECEIVED',
    originalImage: original.originalImage, prediction: null,
    calibratedDefectProbability: null, modelVersion: null, policyVersion: null,
    reviewReason: null, errorMessage: null, gradcamAvailable: false,
    finalJudgement: null, confirmedAt: null, retryOf: original.id, retriedBy: null,
  };
}

function restore(value: unknown): void {
  if (!value || typeof value !== 'object') return;
  const data = value as Partial<PersistedState>;
  if (data.schemaVersion !== 1) {
    warning = '이전 버전의 시연 기록은 읽지 않았습니다.';
    return;
  }
  for (const entry of Array.isArray(data.confirmations) ? data.confirmations : []) {
    if (!entry || typeof entry.id !== 'string' || typeof entry.confirmedAt !== 'string' ||
      (entry.judgement !== 'PASS' && entry.judgement !== 'FAIL')) continue;
    const item = store[entry.id];
    if (item?.status !== 'REVIEW' || item.finalJudgement) continue;
    item.finalJudgement = entry.judgement;
    item.confirmedAt = entry.confirmedAt;
  }
  for (const entry of Array.isArray(data.retries) ? data.retries : []) {
    if (!entry || typeof entry.id !== 'string' || typeof entry.retryOf !== 'string' ||
      typeof entry.capturedAt !== 'string' || !/^INS-R\d+$/.test(entry.id)) continue;
    const original = store[entry.retryOf];
    if (!original || original.status !== 'FAILED' || original.retriedBy || store[entry.id]) continue;
    store[entry.id] = makeRetry(original, entry.id, entry.capturedAt);
    original.retriedBy = entry.id;
    nextRetryNumber = Math.max(nextRetryNumber, Number(entry.id.slice('INS-R'.length)));
  }
}

export function initializeMockInspections(): Promise<void> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) restore(JSON.parse(raw) as unknown);
    } catch (error) {
      warning = '로컬 Mock 기록을 불러오지 못해 기본 시연 데이터로 시작했습니다.';
      console.warn('Mock inspection hydration failed:', error);
    } finally {
      ready = true;
      notify();
    }
  })();
  return initPromise;
}

/** 화면에서 복원 완료까지 판정 버튼을 막고, 저장/복원 변경 시 다시 렌더링합니다. */
export function useMockStoreState(): { ready: boolean; revision: number; warning: string | null } {
  const [state, setState] = useState(() => ({ ready, revision, warning }));
  useEffect(() => {
    const update = () => setState({ ready, revision, warning });
    listeners.add(update);
    void initializeMockInspections().then(update);
    return () => { listeners.delete(update); };
  }, []);
  return state;
}

export function getMockInspection(id: string): Inspection | null {
  const item = store[id];
  return item ? { ...item } : null;
}

export function getMockInspectionHistory(): Inspection[] {
  const retryItems = Object.values(store).filter(item => item.retryOf)
    .sort((a, b) => b.id.localeCompare(a.id));
  const fixedIds = ['INS-008', 'INS-007', 'INS-006', 'INS-005', 'INS-002'];
  return [...retryItems, ...fixedIds.map(id => store[id]).filter((item): item is Inspection => !!item)]
    .map(item => ({ ...item }));
}

// 비동기 저장 중 다른 판정/재검사가 겹치지 않도록 순차 실행합니다.
function exclusive<T>(operation: () => Promise<T>): Promise<T> {
  const work = mutationTail.then(operation, operation);
  mutationTail = work.then(() => undefined, () => undefined);
  return work;
}

/** 실제 서버 연동 시 POST /api/v1/inspections/{id}/confirm으로 교체합니다. */
export async function confirmMockInspection(
  id: string, judgement: 'PASS' | 'FAIL', role: Role
): Promise<Inspection> {
  return exclusive(async () => {
    await initializeMockInspections();
    const item = store[id];
    if (role !== 'WORKER') throw new Error('403: 작업자만 최종 판정할 수 있습니다.');
    if (!item || item.status !== 'REVIEW') throw new Error('409 NOT_REVIEWABLE');
    if (item.finalJudgement) {
      if (item.finalJudgement !== judgement) throw new Error('409 ALREADY_CONFIRMED');
      return { ...item }; // 같은 값 재전송은 기존 결과 반환
    }
    const previous = { ...item };
    item.finalJudgement = judgement;
    item.confirmedAt = new Date().toLocaleString('ko-KR');
    try {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot()));
    } catch (error) {
      store[id] = previous;
      throw new Error('로컬 기록 저장에 실패하여 판정을 확정하지 않았습니다.');
    }
    notify();
    return { ...item };
  });
}

/** 실제 서버 연동 시 POST /api/v1/inspections/{id}/retry로 교체합니다. */
export async function retryMockInspection(id: string): Promise<Inspection> {
  return exclusive(async () => {
    await initializeMockInspections();
    const item = store[id];
    if (!item || item.status !== 'FAILED') throw new Error('409 NOT_RETRYABLE');
    if (item.retriedBy) throw new Error('409 ALREADY_RETRIED');
    nextRetryNumber += 1;
    const newId = `INS-R${nextRetryNumber}`;
    const retry = makeRetry(item, newId, new Date().toLocaleString('ko-KR'));
    store[newId] = retry;
    item.retriedBy = newId;
    try {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot()));
    } catch (error) {
      delete store[newId];
      item.retriedBy = null;
      throw new Error('로컬 기록 저장에 실패하여 재검사를 접수하지 않았습니다.');
    }
    notify();
    return { ...retry };
  });
}
