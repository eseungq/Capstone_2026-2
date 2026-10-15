package com.capstone.inspection.domain.part;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

// 부품별 검사항목 (코드표는 TBD-04)
@Entity
@Table(name = "inspection_item")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InspectionItem {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "part_id")
    private Part part;          // 소속 부품

    @Column(nullable = false, length = 30)
    private String itemCode;    // 예: SCRATCH (임시)

    @Column(nullable = false, length = 50)
    private String name;        // 예: 스크래치
}
