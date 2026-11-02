package com.capstone.inspection.notification;

import com.capstone.inspection.domain.user.DeviceTokenRepository;
import com.capstone.inspection.domain.user.Role;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

// 등록된 WORKER·ADMIN 기기 전체에 푸시 발송 (계약 v4 8.2). 발송 실패는 로그만 남김
// 만료 토큰은 티켓의 DeviceNotRegistered만 삭제 (receipt 미구현)
@Service
@RequiredArgsConstructor
public class PushService {

    private static final Logger log = LoggerFactory.getLogger(PushService.class);
    private static final String DEVICE_NOT_REGISTERED = "DeviceNotRegistered";

    private final DeviceTokenRepository repository;
    private final ExpoPushClient client;
    private final TransactionTemplate tx;

    public record Notice(String type, String inspectionId, String inspectionNo, String partCode, String occurredAt,
                         String title, String body) {
    }

    public void send(Notice notice) {
        List<String> tokens = repository.findTokensByRoles(List.of(Role.WORKER, Role.ADMIN));
        if (tokens.isEmpty()) {
            log.info("푸시 대상 기기 없음 {} {}", notice.type(), notice.inspectionNo());
            return;
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("type", notice.type());
        data.put("inspectionId", notice.inspectionId());
        data.put("inspectionNo", notice.inspectionNo());
        data.put("partCode", notice.partCode());
        data.put("occurredAt", notice.occurredAt());

        int ok = 0;
        List<String> expired = new ArrayList<>();
        for (int from = 0; from < tokens.size(); from += ExpoPushClient.MAX_MESSAGES) {
            List<ExpoPushClient.Message> messages = tokens
                    .subList(from, Math.min(from + ExpoPushClient.MAX_MESSAGES, tokens.size())).stream()
                    .map(token -> new ExpoPushClient.Message(token, notice.title(), notice.body(), data))
                    .toList();
            try {
                for (ExpoPushClient.Ticket ticket : client.send(messages)) {
                    if (ticket.error() == null) {
                        ok++;
                    } else if (DEVICE_NOT_REGISTERED.equals(ticket.error())) {
                        expired.add(ticket.token());
                    } else {
                        log.warn("푸시 티켓 오류 {}: {}", notice.inspectionNo(), ticket.error());
                    }
                }
            } catch (RuntimeException e) {
                log.warn("푸시 발송 실패 {} {}건: {}", notice.inspectionNo(), messages.size(), e.getMessage());
            }
        }
        if (!expired.isEmpty()) {
            tx.executeWithoutResult(status -> repository.deleteByTokens(expired));
        }
        log.info("푸시 발송 {} {} 대상 {}건 성공 {}건 만료 삭제 {}건", notice.type(), notice.inspectionNo(), tokens.size(), ok,
                expired.size());
    }
}
