package com.capstone.inspection.inspection;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository.AutoPassDecision;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository.ReviewTiming;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshot;
import com.capstone.inspection.domain.inspection.RecheckStratum;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.Compare;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.Dwell;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.DwellStats;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.RuleSummary;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.StratumSummary;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.WaitStats;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.Waits;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.function.Predicate;

// 표본 재확인 요약 계산 (계약 6.11). DB 조회 결과만 받아 계산하므로 단위 테스트로 확인
//   - 규칙(시험 이름 포함)이 다른 AUTO_PASS는 섞지 않음. 결정 전 건은 판정 당시 검사에 남긴 규칙으로 묶고 구간도 그 규칙으로 셈
//   - 대기(재확인 전)는 정상·불량 어느 쪽으로도 세지 않음
//   - AUTO_PASS 중 불량 비율 추정 [합의 11/18 김도현]: Σ (구간 AUTO_PASS 건수 ÷ 전체 AUTO_PASS 건수) × (구간 FAIL ÷ 구간 완료)
//     AUTO_PASS가 0건인 구간은 빼고, AUTO_PASS가 있는데 완료가 0건인 구간이 있으면 추정하지 않음 (null)
//   - 가상 비교: drawValue < 비교 비율인 건이 그 비율로 뽑혔을 건. 비교 비율이 실제 비율 이하일 때만 계산 가능
//   - partial: 재확인 대기(가상 비교는 미확인)나 결정 누락이 남으면 true. 먼저 뽑힌 건만 완료된 상태일 수 있어
//     추정이 치우칠 수 있으므로 화면에 안내 [합의 11/18 김도현]
final class RecheckSummary {

    private static final double RATE_TOLERANCE = 1e-9;

    // AUTO_PASS 1건을 규칙 안에서 본 값. decided=false면 sampled·draw·result 없음
    private record Entry(RecheckStratum stratum, boolean decided, boolean sampled, Double draw, Judgement result) {
    }

    // 구간 하나의 건수. 뽑힌 건 중 고른 건(picked)만 sampled·pass·fail로 셈
    private record Counts(long autoPass, long decided, long sampled, long pass, long fail) {

        static Counts of(List<Entry> entries, Predicate<Entry> picked) {
            long decided = 0;
            long sampled = 0;
            long pass = 0;
            long fail = 0;
            for (Entry e : entries) {
                decided += e.decided() ? 1 : 0;
                if (!e.decided() || !e.sampled() || !picked.test(e)) {
                    continue;
                }
                sampled++;
                if (e.result() == Judgement.FAIL) {
                    fail++;
                } else if (e.result() == Judgement.PASS) {
                    pass++;
                }
            }
            return new Counts(entries.size(), decided, sampled, pass, fail);
        }

        long completed() {
            return pass + fail;
        }

        Double failRate() {
            return completed() == 0 ? null : fail / (double) completed();
        }

        Double completionRate() {
            return sampled == 0 ? null : completed() / (double) sampled;
        }

        boolean partial() {
            return sampled > completed() || autoPass > decided;
        }
    }

    // 화면 체류 시간 1건
    private record DwellSample(long ms, int openCount) {
    }

    private RecheckSummary() {
    }

    // rules: 결정·검사에 연결된 규칙 (id → 규칙), compareRule: 비교 비율 (경계는 쓰지 않음), 없으면 null
    static RecheckSummaryResponse build(String partCode, LocalDateTime from, LocalDateTime to,
                                        List<AutoPassDecision> decisions, List<ReviewTiming> reviews,
                                        Map<String, RecheckRuleSnapshot> rules, RecheckRule compareRule) {
        long decided = decisions.stream().filter(d -> d.sampled() != null).count();
        long withoutRule = decisions.stream()
                .filter(d -> d.sampled() == null && d.inspectionRuleId() == null).count();
        List<RuleSummary> summaries = group(decisions, rules).entrySet().stream()
                .map(e -> ruleSummary(e.getKey(), rules.get(e.getKey()), e.getValue(), compareRule))
                .toList();
        return new RecheckSummaryResponse(partCode, Times.toOffset(from), Times.toOffset(to), decisions.size(),
                decided, decisions.size() - decided, withoutRule, summaries, waits(decisions, reviews),
                dwell(decisions, reviews));
    }

    // 규칙 id(V8 결정은 UNRECORDED)별 Entry. 판정 당시 규칙도 결정도 없는 건은 묶지 않음 (undecidedWithoutRuleCount)
    //   순서: UNRECORDED, 그다음 규칙이 만들어진 순
    private static Map<String, List<Entry>> group(List<AutoPassDecision> decisions,
                                                  Map<String, RecheckRuleSnapshot> rules) {
        Map<String, List<Entry>> groups = new TreeMap<>(Comparator
                .comparing((String key) -> !RecheckSummaryResponse.UNRECORDED.equals(key))
                .thenComparing(key -> rules.containsKey(key) ? rules.get(key).getCreatedAt() : LocalDateTime.MIN)
                .thenComparing(Comparator.naturalOrder()));
        for (AutoPassDecision d : decisions) {
            if (d.sampled() != null) {
                String key = d.decisionRuleId() != null ? d.decisionRuleId() : RecheckSummaryResponse.UNRECORDED;
                groups.computeIfAbsent(key, k -> new ArrayList<>())
                        .add(new Entry(d.stratum(), true, d.sampled(), d.drawValue(), d.result()));
            } else if (d.inspectionRuleId() != null && rules.containsKey(d.inspectionRuleId())) {
                RecheckStratum stratum = RecheckRules.stratum(d.calibrated(), d.threshold(),
                        rules.get(d.inspectionRuleId()).toRule());
                groups.computeIfAbsent(d.inspectionRuleId(), k -> new ArrayList<>())
                        .add(new Entry(stratum, false, false, null, null));
            }
        }
        return groups;
    }

    private static RuleSummary ruleSummary(String key, RecheckRuleSnapshot snapshot, List<Entry> entries,
                                           RecheckRule compareRule) {
        Map<RecheckStratum, List<Entry>> byStratum = new EnumMap<>(RecheckStratum.class);
        for (RecheckStratum s : RecheckStratum.values()) {
            byStratum.put(s, entries.stream().filter(e -> e.stratum() == s).toList());
        }
        Map<RecheckStratum, Counts> actual = countEach(byStratum, s -> e -> true);
        List<StratumSummary> strata = actual.entrySet().stream().map(e -> stratumSummary(e.getKey(), e.getValue()))
                .toList();
        Counts total = sum(actual.values());
        RecheckRule rule = snapshot == null ? null : snapshot.toRule();
        return new RuleSummary(snapshot == null ? key : snapshot.getRuleVersion(),
                snapshot == null ? null : snapshot.getTrialName(),
                rule == null ? null : rule.nearRatio(), rule == null ? null : rule.midRatio(),
                rule == null ? null : rule.nearRate(), rule == null ? null : rule.midRate(),
                rule == null ? null : rule.lowRate(),
                total.autoPass(), total.decided(), total.autoPass() - total.decided(), total.sampled(),
                total.sampled() - total.completed(), total.pass(), total.fail(), total.completionRate(),
                total.partial(), strata, estimate(actual.values()), compare(rule, byStratum, compareRule));
    }

    private static StratumSummary stratumSummary(RecheckStratum stratum, Counts c) {
        return new StratumSummary(stratum, c.autoPass(), c.decided(), c.autoPass() - c.decided(), c.sampled(),
                c.completed(), c.sampled() - c.completed(), c.completionRate(), c.pass(), c.fail(), c.failRate());
    }

    // applied: 실제 적용 규칙 (V8 결정이면 null → 비교 불가)
    private static Compare compare(RecheckRule applied, Map<RecheckStratum, List<Entry>> byStratum,
                                   RecheckRule compareRule) {
        if (compareRule == null) {
            return null;
        }
        boolean computable = applied != null && byStratum.entrySet().stream()
                .allMatch(e -> e.getValue().stream().noneMatch(Entry::decided)
                        || compareRule.rateOf(e.getKey()) <= applied.rateOf(e.getKey()) + RATE_TOLERANCE);
        if (!computable) {
            return new Compare(compareRule.nearRate(), compareRule.midRate(), compareRule.lowRate(), false,
                    null, null, null, null, null, null);
        }
        Map<RecheckStratum, Counts> counts = countEach(byStratum, s -> {
            double rate = compareRule.rateOf(s);
            return e -> e.draw() != null && e.draw() < rate;
        });
        Counts total = sum(counts.values());
        return new Compare(compareRule.nearRate(), compareRule.midRate(), compareRule.lowRate(), true,
                total.sampled(), total.sampled() - total.completed(), total.pass(), total.fail(), total.partial(),
                estimate(counts.values()));
    }

    private static Map<RecheckStratum, Counts> countEach(Map<RecheckStratum, List<Entry>> byStratum,
                                                         Function<RecheckStratum, Predicate<Entry>> picked) {
        Map<RecheckStratum, Counts> counts = new EnumMap<>(RecheckStratum.class);
        byStratum.forEach((s, list) -> counts.put(s, Counts.of(list, picked.apply(s))));
        return counts;
    }

    private static Double estimate(Collection<Counts> strata) {
        long autoPass = strata.stream().mapToLong(Counts::autoPass).sum();
        if (autoPass == 0) {
            return null;
        }
        double estimate = 0;
        for (Counts c : strata) {
            if (c.autoPass() == 0) {
                continue; // AUTO_PASS가 없는 구간은 제외
            }
            Double rate = c.failRate();
            if (rate == null) {
                return null; // AUTO_PASS가 있는데 완료 건이 없는 구간이 있으면 전체를 추정하지 않음
            }
            estimate += c.autoPass() / (double) autoPass * rate;
        }
        return estimate;
    }

    private static Counts sum(Collection<Counts> counts) {
        return new Counts(counts.stream().mapToLong(Counts::autoPass).sum(),
                counts.stream().mapToLong(Counts::decided).sum(), counts.stream().mapToLong(Counts::sampled).sum(),
                counts.stream().mapToLong(Counts::pass).sum(), counts.stream().mapToLong(Counts::fail).sum());
    }

    private static Waits waits(List<AutoPassDecision> decisions, List<ReviewTiming> reviews) {
        List<Long> review = reviews.stream().filter(r -> r.confirmedAt() != null && r.completedAt() != null)
                .map(r -> Duration.between(r.completedAt(), r.confirmedAt()).toMillis()).toList();
        long reviewPending = reviews.stream().filter(r -> r.confirmedAt() == null).count();
        List<AutoPassDecision> sampled = decisions.stream().filter(d -> Boolean.TRUE.equals(d.sampled())).toList();
        List<Long> recheck = sampled.stream().filter(d -> d.recheckedAt() != null)
                .map(d -> Duration.between(d.sampledAt(), d.recheckedAt()).toMillis()).toList();
        long recheckPending = sampled.stream().filter(d -> d.result() == null).count();
        return new Waits(waitStats(review, reviewPending), waitStats(recheck, recheckPending));
    }

    private static Dwell dwell(List<AutoPassDecision> decisions, List<ReviewTiming> reviews) {
        return new Dwell(
                dwellStats(reviews.stream().filter(r -> r.screenDwellMs() != null)
                        .map(r -> new DwellSample(r.screenDwellMs(), r.openCount())).toList()),
                dwellStats(decisions.stream().filter(d -> d.screenDwellMs() != null)
                        .map(d -> new DwellSample(d.screenDwellMs(), d.openCount())).toList()));
    }

    private static WaitStats waitStats(List<Long> values, long pending) {
        return new WaitStats(values.size(), pending, average(values), median(values));
    }

    private static DwellStats dwellStats(List<DwellSample> values) {
        List<Long> ms = values.stream().map(DwellSample::ms).toList();
        Double opens = values.isEmpty() ? null : values.stream().mapToInt(DwellSample::openCount).average().orElseThrow();
        return new DwellStats(values.size(), average(ms), median(ms), opens);
    }

    private static Long average(List<Long> values) {
        return values.isEmpty() ? null : Math.round(values.stream().mapToLong(Long::longValue).average().orElseThrow());
    }

    private static Long median(List<Long> values) {
        if (values.isEmpty()) {
            return null;
        }
        List<Long> sorted = values.stream().sorted().toList();
        int mid = sorted.size() / 2;
        return sorted.size() % 2 == 1 ? sorted.get(mid) : Math.round((sorted.get(mid - 1) + sorted.get(mid)) / 2.0);
    }
}
