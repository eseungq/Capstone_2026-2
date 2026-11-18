package com.capstone.inspection.domain.inspection;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

// 상세 화면 체류 시간 (계약 6.11 "화면 체류 시간", V9). 앱이 측정해 REVIEW 확인·재확인 제출과 함께 보냄
//   실제 작업 시간과 다를 수 있음 (화면을 띄워 둔 채 다른 일을 한 경우). 제출하지 않고 나간 건은 기록 없음
@Embeddable
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ScreenTiming {

    @Column(name = "screen_dwell_ms")
    private Long screenDwellMs;           // 화면이 앞에 보이고 앱이 활성인 시간 합

    @Column(name = "first_opened_at")
    private LocalDateTime firstOpenedAt;  // 처음 연 시각 (기기 시계)

    @Column(name = "open_count")
    private Integer openCount;            // 연 횟수 (다시 열 때마다 +1)

    public ScreenTiming(long screenDwellMs, LocalDateTime firstOpenedAt, int openCount) {
        this.screenDwellMs = screenDwellMs;
        this.firstOpenedAt = firstOpenedAt;
        this.openCount = openCount;
    }
}
