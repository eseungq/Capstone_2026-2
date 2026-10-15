package com.capstone.inspection.storage;

import com.capstone.inspection.TestProps;
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponents;
import org.springframework.web.util.UriComponentsBuilder;

import static org.assertj.core.api.Assertions.assertThat;

class ImageUrlSignerTest {

    private final ImageUrlSigner signer = new ImageUrlSigner(TestProps.defaults());

    @Test
    void signedUrlVerifies() {
        ImageUrlSigner.SignedUrl signed = signer.sign("img-1");
        UriComponents uri = UriComponentsBuilder.fromUriString(signed.url()).build();
        assertThat(uri.getPath()).isEqualTo("/api/v1/images/img-1");
        long exp = Long.parseLong(uri.getQueryParams().getFirst("exp"));
        String sig = uri.getQueryParams().getFirst("sig");
        assertThat(signer.verify("img-1", exp, sig)).isTrue();
        assertThat(signer.verify("img-2", exp, sig)).isFalse();      // 다른 이미지
        assertThat(signer.verify("img-1", exp + 1, sig)).isFalse();  // 만료 시각 변조
    }

    @Test
    void expiredUrlRejected() {
        long past = java.time.Instant.now().getEpochSecond() - 1;
        assertThat(signer.verify("img-1", past, "anything")).isFalse();
    }
}
