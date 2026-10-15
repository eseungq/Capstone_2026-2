package com.capstone.inspection.inspection;

// 접수 트랜잭션 커밋 후 분석을 시작하기 위한 이벤트
public record InspectionReceivedEvent(String inspectionId) {
}
