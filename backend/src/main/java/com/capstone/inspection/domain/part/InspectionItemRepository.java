package com.capstone.inspection.domain.part;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface InspectionItemRepository extends JpaRepository<InspectionItem, String> {

    // 검사항목과 소속 부품을 한 번에 조회 (N+1 방지)
    @Query("select i from InspectionItem i join fetch i.part")
    List<InspectionItem> findAllWithPart();

    // 부품의 검사항목 (현재 부품당 1개: 정상·불량 전체 분류, 코드 이름은 TBD-04)
    @Query("select i from InspectionItem i where i.part.id = :partId order by i.itemCode")
    List<InspectionItem> findByPartId(String partId);
}
