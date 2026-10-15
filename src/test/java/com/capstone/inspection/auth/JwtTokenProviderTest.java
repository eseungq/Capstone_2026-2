package com.capstone.inspection.auth;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.auth.security.JwtTokenProvider;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.user.Role;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtTokenProviderTest {

    private final JwtTokenProvider provider = new JwtTokenProvider(TestProps.defaults());

    @Test
    void roundTrip() {
        String token = provider.createAccessToken("user-1", "worker01", Role.WORKER);
        AuthUser user = provider.parse(token);
        assertThat(user.userId()).isEqualTo("user-1");
        assertThat(user.loginId()).isEqualTo("worker01");
        assertThat(user.role()).isEqualTo(Role.WORKER);
    }

    @Test
    void tamperedTokenIsInvalid() {
        String token = provider.createAccessToken("user-1", "worker01", Role.WORKER);
        String tampered = token.substring(0, token.length() - 2) + (token.endsWith("A") ? "BB" : "AA");
        assertThatThrownBy(() -> provider.parse(tampered))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.AUTH_TOKEN_INVALID);
    }

    @Test
    void expiredTokenIsExpired() {
        AppProperties base = TestProps.defaults();
        AppProperties shortTtl = new AppProperties(base.upload(), base.ai(), base.storage(),
                new AppProperties.Auth(base.auth().jwtSecret(), -10, 100, 5), base.inspection());
        String token = new JwtTokenProvider(shortTtl).createAccessToken("u", "w", Role.ADMIN);
        assertThatThrownBy(() -> provider.parse(token))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.AUTH_TOKEN_EXPIRED);
    }
}
