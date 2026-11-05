
import { authV4 } from './authRuntime';
import { createInspectionReadServiceV4 } from './inspectionReadService';
import type { MonitorReaderV4 } from './monitoringPollCore';

/**
 * 실제 백엔드 모니터링 Reader.
 * Mock 데이터와 혼합하지 않습니다.
 *
 * 로그인 이후 SecureStore에 저장된 JWT를 사용합니다.
 */
export const liveMonitoringReaderV4: MonitorReaderV4 =
  createInspectionReadServiceV4({
    mode: 'api',
    transport: authV4,
  });
