package com.capstone.inspection.auth.security;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.user.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

// Access Token 발급·검증 (HS256). Refresh Token은 JWT가 아니라 임의 문자열 (AuthService 참고)
@Component
public class JwtTokenProvider {

    private static final String CLAIM_LOGIN_ID = "loginId";
    private static final String CLAIM_ROLE = "role";
    private static final String CLAIM_TYPE = "typ";
    private static final String TYPE_ACCESS = "access";

    private final SecretKey key;
    private final long accessTtlSeconds;

    public JwtTokenProvider(AppProperties props) {
        byte[] secret = props.auth().jwtSecret().getBytes(StandardCharsets.UTF_8);
        if (secret.length < 32) {
            throw new IllegalStateException("app.auth.jwt-secret은 32바이트 이상이어야 합니다.");
        }
        this.key = Keys.hmacShaKeyFor(secret);
        this.accessTtlSeconds = props.auth().accessTokenTtlSeconds();
    }

    public String createAccessToken(String userId, String loginId, Role role) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(userId)
                .claim(CLAIM_LOGIN_ID, loginId)
                .claim(CLAIM_ROLE, role.name())
                .claim(CLAIM_TYPE, TYPE_ACCESS)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plusSeconds(accessTtlSeconds)))
                .signWith(key)
                .compact();
    }

    public long getAccessTtlSeconds() {
        return accessTtlSeconds;
    }

    // 서명·만료·형식 검증 후 사용자 정보 반환. 만료는 AUTH_TOKEN_EXPIRED, 그 외는 AUTH_TOKEN_INVALID
    public AuthUser parse(String token) {
        try {
            Claims claims = Jwts.parser().verifyWith(key).build()
                    .parseSignedClaims(token).getPayload();
            if (!TYPE_ACCESS.equals(claims.get(CLAIM_TYPE, String.class))) {
                throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
            }
            Role role = Role.valueOf(claims.get(CLAIM_ROLE, String.class));
            return new AuthUser(claims.getSubject(), claims.get(CLAIM_LOGIN_ID, String.class), role);
        } catch (ExpiredJwtException e) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED);
        } catch (JwtException | IllegalArgumentException | NullPointerException e) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
        }
    }
}
