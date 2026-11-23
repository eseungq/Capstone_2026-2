package com.capstone.inspection.config;

import com.capstone.inspection.domain.inspection.RecheckRule;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

// application.yml의 app.* 값을 묶어 두는 설정 객체
// 미확정(TBD) 값은 전부 여기로 모아 코드 수정 없이 바꿀 수 있게 함
@ConfigurationProperties(prefix = "app")
public record AppProperties(Upload upload, Ai ai, Storage storage, Auth auth, Inspection inspection,
                            Monitoring monitoring, Policy policy, Push push,
                            Recheck recheck) {

    // 업로드 제한 (TBD-08)
    public record Upload(List<String> allowedContentTypes, long maxBytes, int minWidth, int minHeight) {
    }

    // AI 서버 호출 설정 (TBD-01, TBD-09)
    // maxResponseStringChars: AI 응답 JSON의 문자열 최대 길이 (Grad-CAM base64가 큼. Jackson 기본 2,000만 자)
    // modelCheck*: 로드 가능 모델 확인 (계약 6.1, 6.2). 성공·실패 결과 캐시 시간과 확인 전용 타임아웃
    // partBaseUrls: 부품별로 다른 AI 서버를 쓸 때 부품 코드 → 주소 (예: FRAME → 8774). 없으면 baseUrl
    public record Ai(String baseUrl, int connectTimeoutMs, int readTimeoutMs, int retryCount,
                     boolean imageSizeCheckEnabled, int maxResponseStringChars,
                     boolean modelCheckEnabled, int modelCheckTtlSeconds, int modelCheckFailureTtlSeconds,
                     int modelCheckConnectTimeoutMs, int modelCheckReadTimeoutMs,
                     Map<String, String> partBaseUrls) {

        // 환경변수로 넣으면 키가 바뀜: APP_AI_PARTBASEURLS_FRAME → "frame", ..._COWL_COVER → "cowl.cover"
        // 그래서 대소문자와 구분 기호(_ . -)를 무시하고 비교
        public String baseUrlFor(String partCode) {
            if (partBaseUrls != null && partCode != null) {
                for (Map.Entry<String, String> e : partBaseUrls.entrySet()) {
                    if (partKey(e.getKey()).equals(partKey(partCode)) && e.getValue() != null && !e.getValue().isBlank()) {
                        return e.getValue();
                    }
                }
            }
            return baseUrl;
        }

        private static String partKey(String code) {
            return code.replaceAll("[_.\\-]", "").toUpperCase(java.util.Locale.ROOT);
        }

        // 모델 목록을 조회할 AI 서버 전체 (기본 주소 먼저, 중복 제거)
        public List<String> allBaseUrls() {
            LinkedHashSet<String> urls = new LinkedHashSet<>();
            urls.add(baseUrl);
            if (partBaseUrls != null) {
                partBaseUrls.values().stream().filter(v -> v != null && !v.isBlank()).forEach(urls::add);
            }
            return List.copyOf(urls);
        }

    }

    // 이미지 저장소 설정 (TBD-01)
    public record Storage(String type, String localRoot, int accessUrlTtlSeconds, String publicBaseUrl) {
    }

    // 인증 설정 (TBD-10)
    public record Auth(String jwtSecret, long accessTokenTtlSeconds, long refreshTokenTtlSeconds,
                       int loginLockThreshold) {
    }

    // 비동기 분석 스레드 풀 (계약 5장)
    public record Inspection(int analysisPoolSize, int analysisQueueCapacity) {
    }

    // 모니터링 화면 (계약 6.3): 부품별 최근 검사 표시 건수
    public record Monitoring(int recentSize) {
    }

    // 정책 등록 시 ready 판정 기준 (TBD-03 임시)
    public record Policy(int minSampleCount) {
    }

    // Expo 푸시 발송 (계약 8장). enabled=false면 로그만 남김
    public record Push(boolean enabled, String expoUrl, int connectTimeoutMs, int readTimeoutMs) {
    }

    // AUTO_PASS 표본 재확인 (계약 6.11, TBD-16). 구간은 보정 확률 ÷ 적용 기준치 r로 나눔
    //   r ≥ nearRatio → NEAR, r ≥ midRatio → MID, 나머지 LOW. 비율 0이면 그 구간은 뽑지 않음
    //   trialName: 같은 설정으로 여러 번 시험할 때 회차 구분 (선택, 예: 공동시험 1차). 빈 값은 null
    public record Recheck(boolean enabled, double nearRatio, double midRatio, double nearRate, double midRate,
                          double lowRate, String trialName) {

        // 잘못된 값이면 기동 시 실패 (그대로 두면 DB CHECK 위반으로 표본이 조용히 안 뽑힘)
        public Recheck {
            trialName = trialName == null || trialName.isBlank() ? null : trialName.trim();
            if (trialName != null && trialName.length() > 60) {
                throw new IllegalArgumentException("app.recheck.trial-name은 60자 이하여야 합니다.");
            }
            if (!(0 <= midRatio && midRatio <= nearRatio && nearRatio <= 1)) {
                throw new IllegalArgumentException("app.recheck: 0 ≤ mid-ratio ≤ near-ratio ≤ 1 이어야 합니다.");
            }
            for (double rate : new double[]{nearRate, midRate, lowRate}) {
                if (!(rate == 0 || (rate >= 0.000001 && rate <= 1))) {
                    throw new IllegalArgumentException("app.recheck: 비율은 0 또는 0.000001~1 이어야 합니다.");
                }
            }
        }

        // 결정 행에 남길 규칙 값 (계약 6.11). DB DECIMAL(7,6)에 맞춰 소수 6자리
        public RecheckRule rule() {
            return new RecheckRule(round6(nearRatio), round6(midRatio), round6(nearRate), round6(midRate),
                    round6(lowRate));
        }

        private static double round6(double value) {
            return Math.round(value * 1_000_000) / 1_000_000.0;
        }
    }
}
