# 응답 예시

GOOD/DEFECT의 점수와 시간은 연결 시험에서 확인한 값이며 UUID는 예시로 바꿨습니다. 새 성능 평가 자료가 아닙니다.
`defect.json`의 imageBase64는 공개 사진 업로드를 피하기 위해 앞부분만 남겼습니다. 완전한 JPEG로 디코딩하거나 API 회귀 시험 입력으로 사용하지 마세요.
두 NO_ACTIVATION 예시는 강제로 구성한 ZERO_MAP/CONSTANT_MAP 계약 예시입니다. 현재 e02에서 자연 발생하는 DEFECT 사진을 확인했다는 뜻이 아닙니다. B6 실제 사례 시험은 보류입니다.
`models.json`은 실제 모델 목록 형식입니다. `error.json`은 HTTP 409 오류 본문 형식입니다.
GOOD는 gradcam=null, DEFECT 생성 성공은 JPEG, CAM 실패만 발생한 경우도 gradcam=null입니다. 보정 미준비 시 보정 확률/보정기 버전은 모두 null입니다.
