package com.capstone.inspection.domain.model;

import com.capstone.inspection.domain.part.InspectionItem;
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

import java.time.LocalDateTime;

// 검사항목별 AI 모델 버전. 모델 파일은 AI 서버에 있고 여기에는 메타데이터만 저장
@Entity
@Table(name = "ai_model")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AiModel {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "item_id")
    private InspectionItem item;              // 대응 검사항목

    @Column(nullable = false, unique = true, length = 100)
    private String modelVersion;              // 전처리·패치·집계·보정 설정까지 추적하는 버전

    @Column(nullable = false, columnDefinition = "json")
    private String pipelineConfigJson;        // 파이프라인 설정 원문(JSON 문자열)

    @Column(nullable = false, length = 128)
    private String checksum;                  // 모델 파일 체크섬

    @Column(columnDefinition = "json")
    private String metricsJson;               // 평가 지표

    @Column(nullable = false)
    private boolean patchInspectionSupported; // v4에서는 사용하지 않음 (과거 기록용)

    @Column(nullable = false)
    private boolean active;                   // 검사항목당 활성 모델 1개 (서비스에서 보장)

    @Column(length = 100)
    private String calibratorVersion;         // 이 모델에 맞춘 보정기 버전 (없으면 null)

    @Column(nullable = false)
    private LocalDateTime createdAt;
}
