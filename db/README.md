# db · DB 설계

담당: 김남균

이 폴더에 들어갈 것
- DB 설계 SQL (스키마, 예시 데이터, 조회·저장 흐름, 제약 위반 테스트)
- ERD

실제 서버에 적용되는 스키마는 백엔드의 Flyway 마이그레이션입니다: [backend/src/main/resources/db/migration](../backend/src/main/resources/db/migration) (V1~V4 적용됨).
설계를 바꿀 때는 **이미 적용된 V1~V4는 수정하지 않고** 다음 버전(V5~) 파일로 추가합니다.

저장 구조 기준: [계약 v4 9장](../docs/백엔드_API계약_v4.md#9-저장-구조-변경안-김남균-협의)
