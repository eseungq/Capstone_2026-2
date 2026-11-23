package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.user.User;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
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
import com.capstone.inspection.common.time.Times;

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

    // 결정할 때 쓴 규칙 (V9). V8로 기록된 행은 셋 다 null
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "rule_id")
    private RecheckRuleSnapshot rule;
    private Double ratio;               // 보정 확률 ÷ 적용 기준치
    private Double drawValue;           // 검사 ID로 정한 0~1 값. 비율이 이보다 크면 뽑힘

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Judgement result;           // 재확인 전이면 null

    @Column(length = 200)
    private String comment;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "rechecked_by")
    private User recheckedBy;

    private LocalDateTime recheckedAt;

    @Embedded
    private ScreenTiming screenTiming;  // 재확인 화면 체류 시간 (선택, V9)

    // 관리자 확인함 (V9): 재확인 FAIL을 관리자가 봤다는 기록. 문제 해결 완료가 아님
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "acknowledged_by")
    private User acknowledgedBy;

    private LocalDateTime acknowledgedAt;

    @Column(length = 200)
    private String acknowledgeNote;

    public AutoPassRecheck(Inspection inspection, boolean sampled, RecheckStratum stratum, double samplingRate,
                           RecheckRuleSnapshot rule, double ratio, double drawValue) {
        this.id = UUID.randomUUID().toString();
        this.inspection = inspection;
        this.sampled = sampled;
        this.stratum = stratum;
        this.samplingRate = samplingRate;
        this.sampledAt = Times.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        this.rule = rule;
        this.ratio = ratio;
        this.drawValue = drawValue;
    }
}
