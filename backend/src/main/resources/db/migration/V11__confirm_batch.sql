-- V11: 일괄 FAIL (계약 v4 6.7.1, 김남균 협의)
--   - worker_confirmation.batch_id: 일괄 요청 1건에서 저장된 판정 묶음 ID (UUID). NULL이면 단건 확인(6.7)
--   - 재전송으로 새 batchId가 생겨도 이미 저장된 건은 바뀌지 않으므로 처음 저장한 요청의 값만 남음
--   - 지금은 batch_id로 조회하는 API가 없어 인덱스는 두지 않음 (조회가 생기면 그때 추가)
ALTER TABLE worker_confirmation
    ADD COLUMN batch_id CHAR(36) NULL;
