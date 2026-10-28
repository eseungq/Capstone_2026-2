package com.capstone.inspection.domain.inspection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

// 의심 패치 1개. 좌표는 방향 보정된 표시 원본 기준 0~1 정규화 [x, y, w, h]
@Entity
@Table(name = "defect_detection")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class DefectDetection {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inspection_id")
    private Inspection inspection;

    @Column(nullable = false, length = 50)
    private String patchId;              // 검사 안에서 유일

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private LocationType locationType;   // PATCH_BBOX

    @Column(nullable = false, columnDefinition = "json")
    private String coordinatesJson;      // 예: [0.12, 0.40, 0.08, 0.06]

    @Column(nullable = false)
    private Double patchScore;           // 패치 의심 점수 (사진 단위 확률로 쓰지 않음)

    @Column(nullable = false, length = 50)
    private String defectType;
}
