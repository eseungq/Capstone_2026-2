package com.capstone.inspection.domain.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "users") // user는 MySQL 예약어라 users 사용
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED) // JPA용 기본 생성자
public class User {

    @Id
    @Column(length = 36)
    private String id;                  // UUID 문자열

    @Column(nullable = false, unique = true, length = 50)
    private String loginId;             // 로그인 아이디

    @Column(nullable = false, length = 100)
    private String passwordHash;        // BCrypt 해시 (평문 저장 금지)

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Role role;                  // WORKER, ADMIN, DEVICE

    @Column(nullable = false)
    private int failedLoginCount;       // 연속 로그인 실패 횟수 (잠금 기준 TBD-10)

    @Column(nullable = false)
    private boolean locked;             // 잠금 여부

    @Column(nullable = false)
    private LocalDateTime createdAt;

    public User(String loginId, String passwordHash, Role role) {
        this.id = UUID.randomUUID().toString();
        this.loginId = loginId;
        this.passwordHash = passwordHash;
        this.role = role;
        this.failedLoginCount = 0;
        this.locked = false;
        this.createdAt = LocalDateTime.now();
    }

    // 로그인 실패 1회 기록. 기준 횟수에 도달하면 잠금 (TBD-10)
    public void recordLoginFailure(int lockThreshold) {
        this.failedLoginCount++;
        if (lockThreshold > 0 && this.failedLoginCount >= lockThreshold) {
            this.locked = true;
        }
    }

    // 로그인 성공 시 실패 횟수 초기화
    public void resetLoginFailures() {
        this.failedLoginCount = 0;
    }
}
