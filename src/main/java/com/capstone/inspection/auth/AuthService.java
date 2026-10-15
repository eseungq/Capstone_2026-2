package com.capstone.inspection.auth;

import com.capstone.inspection.auth.dto.TokenResponse;
import com.capstone.inspection.auth.security.JwtTokenProvider;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.user.RefreshToken;
import com.capstone.inspection.domain.user.RefreshTokenRepository;
import com.capstone.inspection.domain.user.User;
import com.capstone.inspection.domain.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;

// 로그인·토큰 재발급·로그아웃 (FR-BE-01)
@Service
@RequiredArgsConstructor
public class AuthService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final UserRepository userRepository;
    private final RefreshTokenRepository refreshTokenRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider tokenProvider;
    private final AppProperties props;

    // 실패 횟수를 저장해야 하므로 실패해도 커밋되도록 noRollbackFor 지정
    @Transactional(noRollbackFor = BusinessException.class)
    public TokenResponse login(String loginId, String password) {
        User user = userRepository.findByLoginId(loginId)
                .orElseThrow(() -> new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS));
        if (user.isLocked()) {
            throw new BusinessException(ErrorCode.AUTH_ACCOUNT_LOCKED);
        }
        if (!passwordEncoder.matches(password, user.getPasswordHash())) {
            user.recordLoginFailure(props.auth().loginLockThreshold());
            throw new BusinessException(user.isLocked() ? ErrorCode.AUTH_ACCOUNT_LOCKED : ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        user.resetLoginFailures();
        return issueTokens(user);
    }

    // Refresh Token 회전: 사용한 토큰은 폐기하고 새 토큰 쌍 발급
    @Transactional(noRollbackFor = BusinessException.class)
    public TokenResponse refresh(String refreshToken) {
        RefreshToken saved = refreshTokenRepository.findByTokenHashWithUser(hash(refreshToken))
                .orElseThrow(() -> new BusinessException(ErrorCode.AUTH_TOKEN_INVALID));
        if (!saved.isUsable(LocalDateTime.now())) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
        }
        User user = saved.getUser();
        if (user.isLocked()) {
            throw new BusinessException(ErrorCode.AUTH_ACCOUNT_LOCKED);
        }
        saved.revoke();
        return issueTokens(user);
    }

    // 본인 토큰만 폐기. 없는 토큰이어도 로그아웃은 성공으로 처리 (앱이 로컬 토큰을 지우면 끝)
    @Transactional
    public void logout(String userId, String refreshToken) {
        if (refreshToken == null || refreshToken.isBlank()) {
            return;
        }
        refreshTokenRepository.findByTokenHashWithUser(hash(refreshToken))
                .filter(t -> t.getUser().getId().equals(userId))
                .ifPresent(RefreshToken::revoke);
    }

    private TokenResponse issueTokens(User user) {
        String accessToken = tokenProvider.createAccessToken(user.getId(), user.getLoginId(), user.getRole());
        String refreshToken = newRefreshToken();
        LocalDateTime expiresAt = LocalDateTime.now().plusSeconds(props.auth().refreshTokenTtlSeconds());
        refreshTokenRepository.save(new RefreshToken(user, hash(refreshToken), expiresAt));
        return new TokenResponse(accessToken, refreshToken, "Bearer", tokenProvider.getAccessTtlSeconds(),
                new TokenResponse.UserInfo(user.getId(), user.getLoginId(), user.getRole()));
    }

    private static String newRefreshToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static String hash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
