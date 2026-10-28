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

// REVIEW 검사에 대한 작업자 최종 판정 (AI 결과와 분리 저장)
@Entity
@Table(name = "worker_confirmation")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class WorkerConfirmation {

    @Id
    @Column(length = 36)
    private String id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inspection_id", unique = true)
    private Inspection inspection;     // 검사당 최대 1건

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "worker_id")
    private User worker;               // 확인자

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Judgement finalJudgement;  // PASS 또는 FAIL

    @Column(nullable = false)
    private LocalDateTime confirmedAt; // 확인 시각 (감사 정보)

    @Column(length = 200)
    private String comment;            // 작업자 메모 (선택)

    public WorkerConfirmation(Inspection inspection, User worker, Judgement finalJudgement, String comment) {
        this.id = UUID.randomUUID().toString();
        this.inspection = inspection;
        this.worker = worker;
        this.finalJudgement = finalJudgement;
        this.comment = comment;
        this.confirmedAt = LocalDateTime.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
    }
}
