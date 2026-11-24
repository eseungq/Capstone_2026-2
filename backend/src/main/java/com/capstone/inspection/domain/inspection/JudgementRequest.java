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
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

// 판정 확인 요청·정정 (계약 6.12, V12). 최초 판정은 inspection에 그대로 두고 요청·처리 기록만 따로 저장
//   open_key(검사당 대기 1건용 생성 컬럼)는 DB가 계산하므로 매핑하지 않음
@Entity
@Table(name = "judgement_request")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class JudgementRequest {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inspection_id")
    private Inspection inspection;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "requested_by")
    private User requestedBy;

    @Column(nullable = false)
    private LocalDateTime requestedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Judgement originalJudgement;   // 검사의 최초 판정

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Judgement currentJudgement;    // 요청 당시 현재 판정 (앞선 정정이 있으면 그 값)

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Judgement claimedJudgement;    // 작업자가 확인한 판정

    @Column(length = 100)
    private String area;                   // 부위 (선택)

    @Column(nullable = false, length = 500)
    private String reason;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private JudgementRequestStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "resolved_by")
    private User resolvedBy;               // 처리 전이면 null

    private LocalDateTime resolvedAt;

    @Column(length = 500)
    private String resolveNote;

    public JudgementRequest(Inspection inspection, User requestedBy, Judgement currentJudgement,
                            Judgement claimedJudgement, String area, String reason) {
        this.id = UUID.randomUUID().toString();
        this.inspection = inspection;
        this.requestedBy = requestedBy;
        this.requestedAt = LocalDateTime.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        this.originalJudgement = inspection.getFinalJudgement();
        this.currentJudgement = currentJudgement;
        this.claimedJudgement = claimedJudgement;
        this.area = area;
        this.reason = reason;
        this.status = JudgementRequestStatus.OPEN;
    }
}
