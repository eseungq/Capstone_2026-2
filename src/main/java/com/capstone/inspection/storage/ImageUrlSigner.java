package com.capstone.inspection.storage;

import com.capstone.inspection.config.AppProperties;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;

// 만료되는 이미지 접근 주소 발급·검증 (계약 v4 6.5, 7.1)
// URL: {publicBaseUrl}/api/v1/images/{imageId}?exp={만료 epoch 초}&sig={HMAC-SHA256}
@Component
public class ImageUrlSigner {

    private final byte[] secret;
    private final String baseUrl;
    private final int ttlSeconds;

    public ImageUrlSigner(AppProperties props) {
        this.secret = ("image-url:" + props.auth().jwtSecret()).getBytes(StandardCharsets.UTF_8);
        String base = props.storage().publicBaseUrl();
        this.baseUrl = base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
        this.ttlSeconds = props.storage().accessUrlTtlSeconds();
    }

    public record SignedUrl(String url, Instant expiresAt) {
    }

    public SignedUrl sign(String imageId) {
        Instant expiresAt = Instant.now().plusSeconds(ttlSeconds);
        long exp = expiresAt.getEpochSecond();
        String url = baseUrl + "/api/v1/images/" + imageId + "?exp=" + exp + "&sig=" + signature(imageId, exp);
        return new SignedUrl(url, expiresAt);
    }

    public boolean verify(String imageId, long exp, String sig) {
        if (sig == null || Instant.now().getEpochSecond() > exp) {
            return false;
        }
        byte[] expected = signature(imageId, exp).getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, sig.getBytes(StandardCharsets.UTF_8)); // 시간 일정 비교
    }

    private String signature(String imageId, long exp) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] raw = mac.doFinal((imageId + ":" + exp).getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }
}
