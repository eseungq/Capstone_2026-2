package com.capstone.inspection.common.time;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.TimeZone;

import static org.assertj.core.api.Assertions.assertThat;

// JVM 기본 시간대를 UTC로 바꿔도 Times 계산이 서울 기준인지 확인 (DB 왕복은 DailyHistoryIntegrationTest를 TZ=UTC로 실행해 확인)
class TimesTest {

    private static final ZoneId UTC = ZoneId.of("UTC");
    private static final Duration CLOCK_TOLERANCE = Duration.ofSeconds(5);

    private TimeZone original;

    @BeforeEach
    void useUtcJvm() {
        original = TimeZone.getDefault();
        TimeZone.setDefault(TimeZone.getTimeZone(UTC));
    }

    @AfterEach
    void restore() {
        TimeZone.setDefault(original);
    }

    @Test
    @DisplayName("UTC JVM에서도 저장 시각은 서울 시각")
    void nowIsSeoulOnUtcJvm() {
        LocalDateTime seoulNow = LocalDateTime.now(Times.ZONE);

        LocalDateTime stored = Times.now();

        assertThat(ZoneId.systemDefault()).isEqualTo(UTC);
        assertThat(Duration.between(seoulNow, stored).abs()).isLessThan(CLOCK_TOLERANCE);
        assertThat(Times.today()).isEqualTo(LocalDate.now(Times.ZONE));
    }

    @Test
    @DisplayName("UTC JVM에서 서울 11/23 23:30 기록은 11/23로 셈 (11/24로 넘어가지 않음)")
    void seoulRecordStaysOnSameKstDateOnUtcJvm() {
        LocalDateTime stored = LocalDateTime.of(2026, 11, 23, 23, 30);

        assertThat(Times.kstDate(stored)).isEqualTo(LocalDate.of(2026, 11, 23));
    }

    @Test
    @DisplayName("UTC JVM에서 날짜 범위 경계는 서울 0시, API 출력도 +09:00")
    void boundaryAndOffsetAreSeoulOnUtcJvm() {
        LocalDate date = LocalDate.of(2026, 11, 23);

        assertThat(Times.kstStartOfDay(date)).isEqualTo(LocalDateTime.of(2026, 11, 23, 0, 0));
        assertThat(Times.toOffset(LocalDateTime.of(2026, 11, 23, 23, 30)).toString())
                .isEqualTo("2026-11-23T23:30+09:00");
    }
}
