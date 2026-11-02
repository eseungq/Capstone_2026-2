package com.capstone.inspection.ai;

// 활성 모델을 AI 서버에서 쓸 수 있는지 (계약 v4 6.1, 6.2)
//   AVAILABLE    목록에 있고 loadable=true → 정상 접수
//   NOT_LOADABLE 목록에 없거나 loadable=false → 기록 없이 422
//   UNKNOWN      연결 실패·타임아웃·형식 오류·404 → 접수는 받고 분석 단계에서 판단 (AI 오류면 FAILED)
public enum ModelAvailability {
    AVAILABLE, NOT_LOADABLE, UNKNOWN
}
