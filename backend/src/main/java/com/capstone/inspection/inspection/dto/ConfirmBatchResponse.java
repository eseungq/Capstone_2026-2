package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;

import java.time.OffsetDateTime;
import java.util.List;

// POST /inspections/confirm-batch 응답 (계약 v4 6.7.1). results는 요청 순서 그대로
public record ConfirmBatchResponse(String batchId, List<Result> results) {

    public ConfirmBatchResponse {
        results = List.copyOf(results);
    }

    // 건별 결과 종류 (괄호는 6.7 단건이었다면의 응답)
    public enum Outcome {
        CONFIRMED,          // 이번 요청으로 저장 (200)
        ALREADY_CONFIRMED,  // 이미 FAIL로 확정. 처음 기록을 돌려줌 (200 같은 값 재전송)
        CONFLICT,           // 이미 PASS로 확정, 덮어쓰지 않음 (409 ALREADY_CONFIRMED)
        NOT_REVIEWABLE,     // REVIEW 대기가 아님 (409 NOT_REVIEWABLE)
        NOT_FOUND,          // 없는 검사 (404 INSPECTION_NOT_FOUND)
        ERROR               // 계약 표 밖: 그 건만 서버 오류로 저장 못 함 (500 INTERNAL_SERVER_ERROR). 다시 보내면 됨
    }

    // 실패 결과는 현재 값이 있으면 채우고 errorCode에 6.7과 같은 코드
    public record Result(String inspectionId,
                         String inspectionNo,
                         Outcome result,
                         Judgement finalJudgement,
                         JudgedBy judgedBy,
                         String confirmedBy,       // 확인한 작업자 loginId
                         OffsetDateTime confirmedAt,
                         ErrorCode errorCode) {

        public static Result of(String inspectionId, Outcome outcome, ConfirmResponse current, ErrorCode errorCode) {
            if (current == null) {
                return new Result(inspectionId, null, outcome, null, null, null, null, errorCode);
            }
            return new Result(inspectionId, current.inspectionNo(), outcome, current.finalJudgement(),
                    current.judgedBy(), current.confirmedBy(), current.confirmedAt(), errorCode);
        }
    }
}
