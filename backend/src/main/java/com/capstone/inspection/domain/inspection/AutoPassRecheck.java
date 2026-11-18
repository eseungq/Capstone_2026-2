package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.user.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

// AUTO_PASS 표본 재확인 (계약 6.11, V8). 시스템 판정은 inspection에 그대로 두고 재확인 결과만 따로 저장
//   AUTO_PASS마다 추출 결정을 1행 남김. 행이 없으면 결정 전이거나 저장 실패 → RecheckSweeper가 다시 처리
@Entity
@Table(name = "auto_pass_recheck")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AutoPassRecheck {

    @Id
    @Column(length = 36)
    private String id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inspection_id", unique = true)
    private Inspection inspection;      // 검사당 최대 1건

    @Column(nullable = false)
    private boolean sampled;            // 재확인 대상으로 뽑혔는지 (뽑히지 않은 결정도 1행 남김)

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private RecheckStratum stratum;

    @Column(nullable = false)
    private double samplingRate;        // 이 구간의 추출 비율 (집계 가중치 1/rate)

    @Column(nullable = false)
    private LocalDateTime sampledAt;    // 추출 결정 시각

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Judgement result;           // 재확인 전이면 null

    @Column(length = 200)
    private String comment;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "rechecked_by")
    private User recheckedBy;

    private LocalDateTime recheckedAt;

    public AutoPassRecheck(Inspection inspection, boolean sampled, RecheckStratum stratum, double samplingRate) {
        this.id = UUID.randomUUID().toString();
        this.inspection = inspection;
        this.sampled = sampled;
        this.stratum = stratum;
        this.samplingRate = samplingRate;
        this.sampledAt = LocalDateTime.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
    }
}
