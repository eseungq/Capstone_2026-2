# mobile · 작업자·관리자 앱

담당: 홍승인

이 폴더에 들어갈 것
- React Native (Expo Router) 앱 코드
- 실행 방법 (Expo Go, 연결할 백엔드 주소 설정 방법)

연동 기준: [계약 v4 6장 API](../docs/백엔드_API계약_v4.md#6-api), 알림은 [8장](../docs/백엔드_API계약_v4.md#8-알림-계약-홍승인-확인-필요)

> iPhone에서 `localhost`는 개발 PC가 아니므로 백엔드 주소는 PC의 내부 IP로 설정합니다 ([backend README](../backend/README.md) 참고).


## 도어 30% → 35% AUTO_PASS 독립 Mock 시연 (2026-11-09 합의)

- 시연 대상: `mock-door-swin-t-v1` / `example-door-demo-30`, 기준치 `0.30`, 허용 범위 `0.2801~0.3752`.
- 시연 입력: `GOOD` 예측, 보정 불량 확률 `0.32`. 새 버전 `example-door-demo-30-t1`의 조정 기준치는 `0.35`.
- **실제 e02와 별개**: DGX e02의 `calibratedDefectProbability`와 `calibratorVersion`은 미제공(`null`)이며, 실서버 응답은 계속 `REVIEW`. 시연 30% 결과는 동일 평가 사진에 사후 적용한 값으로 독립 검증된 운영 정책이 아닙니다.
- `src/api/backendV4/demoPolicyScenarioV4.ts`의 판정 함수는 이 Mock 화면에만 사용합니다. 실서버 응답은 절대로 앱에서 재판정하지 않습니다.

### iPhone 시연 절차

1. Expo Go에서 **Mock 관리자**로 이동해 설정 → 자동 통과 기준 → 정책 조정 화면 → **DOOR 30% → 35% 정책 조정 · 독립 Mock 시연**에 들어갑니다.
2. **GOOD / 32% 새 검사 접수 · Mock**을 눌러 30% 기준에서 `REVIEW`를 확인합니다.
3. `passThreshold`에 `0.35`를 입력하고 **새 정책 버전 저장 · Mock**을 누릅니다. 저장만 하고 같은 입력을 다시 접수하면 여전히 `REVIEW`입니다.
4. **저장된 새 정책 적용 · Mock**을 누른 뒤 같은 입력을 새 검사로 접수합니다. 새 Mock 검사만 `AUTO_PASS · SYSTEM 최종 PASS`로 표시됩니다. 이전 REVIEW 시연 기록은 유지됩니다.
5. 화면에 **서버 API 요청 없음**, **운영 정책/검사 기록 변경 없음**이 표시되는지 확인합니다. 실제 API 연결 화면에서는 반환된 `displayState`를 그대로 사용하고 REVIEW_PENDING만 작업자 판정으로 연결합니다.

### 검증

```powershell
cd mobile
npx tsc --noEmit
```

GitHub에서 작성한 코드는 iPhone/TypeScript 로컬 검증을 완료하기 전까지 Draft PR로 유지합니다. 실제 백엔드 Mock 시연 API의 등록·저장·적용 시험은 별도로 수행해야 하며 이 화면만으로 API 통합시험을 통과했다고 보고하지 않습니다.
