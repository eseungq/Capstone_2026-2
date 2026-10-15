package com.capstone.inspection.domain.part;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

// 부품 마스터 (11종, V2__seed_parts.sql에서 등록)
@Entity
@Table(name = "part")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Part {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, unique = true, length = 30)
    private String partCode;   // 예: DOOR

    @Column(nullable = false, length = 50)
    private String name;       // 예: 도어
}
