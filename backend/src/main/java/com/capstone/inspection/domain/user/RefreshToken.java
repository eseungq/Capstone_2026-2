package com.capstone.inspection.domain.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

// 발급한 Refresh Token. 원문은 저장하지 않고 SHA-256 해시만 보관
@Entity
@Table(name = "refresh_token")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RefreshToken {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id")
    private User user;

    @Column(nullable = false, unique = true, length = 64)
    private String tokenHash;

    @Column(nullable = false)
    private LocalDateTime expiresAt;

    private LocalDateTime revokedAt;      // 폐기 시각 (로그아웃·재발급)

    @Column(nullable = false)
    private LocalDateTime createdAt;

    public RefreshToken(User user, String tokenHash, LocalDateTime expiresAt) {
        this.id = UUID.randomUUID().toString();
        this.user = user;
        this.tokenHash = tokenHash;
        this.expiresAt = expiresAt;
        this.createdAt = LocalDateTime.now();
    }

    public boolean isUsable(LocalDateTime now) {
        return revokedAt == null && expiresAt.isAfter(now);
    }

    public void revoke() {
        if (revokedAt == null) {
            revokedAt = LocalDateTime.now();
        }
    }
}
