package com.capstone.inspection.domain.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;

public interface DeviceTokenRepository extends JpaRepository<DeviceToken, String> {

    // 같은 토큰이 있으면 사용자·플랫폼·최근 확인 시각 갱신. 동시 등록에도 행은 1개 (token UNIQUE)
    @Modifying
    @Query(value = """
            insert into device_token (id, user_id, token, platform, created_at, last_seen_at)
            values (:id, :userId, :token, :platform, :now, :now) as new_row
            on duplicate key update user_id = new_row.user_id, platform = new_row.platform,
                                    last_seen_at = new_row.last_seen_at""", nativeQuery = true)
    void upsert(String id, String userId, String token, String platform, LocalDateTime now);

    // 본인 토큰만 해제
    @Modifying
    @Query("delete from DeviceToken d where d.token = :token and d.user.id = :userId")
    int deleteOwn(String token, String userId);

    // 만료 토큰 정리 (Expo DeviceNotRegistered)
    @Modifying
    @Query("delete from DeviceToken d where d.token in :tokens")
    int deleteByTokens(Collection<String> tokens);

    // 발송 대상 역할의 토큰 전체
    @Query("select d.token from DeviceToken d where d.user.role in :roles")
    List<String> findTokensByRoles(Collection<Role> roles);
}
