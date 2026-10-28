package com.capstone.inspection.inspection;

import com.capstone.inspection.ai.AiPredictResponse.Gradcam;
import com.capstone.inspection.domain.inspection.GradcamStatus;
import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;

// DEFECT 예측의 Grad-CAM 처리 규칙 (합의 10/28)
class GradcamParserTest {

    private static final String PNG = base64("png");
    private static final String JPEG = base64("jpg");

    private static String base64(String format) {
        try {
            BufferedImage img = new BufferedImage(40, 30, BufferedImage.TYPE_INT_RGB);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            ImageIO.write(img, format, out);
            return Base64.getEncoder().encodeToString(out.toByteArray());
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    private static GradcamStatus status(Gradcam g) {
        return GradcamParser.parse("insp-1", g).status();
    }

    @Test
    void nullIsFailed() {
        assertThat(status(null)).isEqualTo(GradcamStatus.FAILED);
    }

    @Test
    void noActivationHasNoImage() {
        GradcamParser.Parsed p = GradcamParser.parse("insp-1",
                new Gradcam("DEFECT", "NO_ACTIVATION", "ZERO_MAP", null, null));
        assertThat(p.status()).isEqualTo(GradcamStatus.NO_ACTIVATION);
        assertThat(p.bytes()).isNull();
        assertThat(status(new Gradcam("DEFECT", "NO_ACTIVATION", "CONSTANT_MAP", null, null)))
                .isEqualTo(GradcamStatus.NO_ACTIVATION);
    }

    @Test
    void generatedPng() {
        GradcamParser.Parsed p = GradcamParser.parse("insp-1", new Gradcam("DEFECT", "GENERATED", null, "png", PNG));
        assertThat(p.status()).isEqualTo(GradcamStatus.GENERATED);
        assertThat(p.info().contentType()).isEqualTo("image/png");
        assertThat(p.info().extension()).isEqualTo("png");
        assertThat(p.info().width()).isEqualTo(40);
        assertThat(p.info().height()).isEqualTo(30);
    }

    @Test
    void generatedJpegAndAliases() {
        GradcamParser.Parsed p = GradcamParser.parse("insp-1", new Gradcam("DEFECT", "GENERATED", null, "jpeg", JPEG));
        assertThat(p.status()).isEqualTo(GradcamStatus.GENERATED);
        assertThat(p.info().contentType()).isEqualTo("image/jpeg");
        assertThat(p.info().extension()).isEqualTo("jpg");
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "jpg", JPEG))).isEqualTo(GradcamStatus.GENERATED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "JPEG", JPEG))).isEqualTo(GradcamStatus.GENERATED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "PNG", PNG))).isEqualTo(GradcamStatus.GENERATED);
    }

    @Test
    void missingStatusWithValidImageIsGenerated() {
        // 10/28 이전 형식 (status 없음)
        assertThat(status(new Gradcam("DEFECT", null, null, "png", PNG))).isEqualTo(GradcamStatus.GENERATED);
    }

    @Test
    void invalidCasesAreFailed() {
        assertThat(status(new Gradcam("DEFECT", "SOMETHING", null, "png", PNG))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("GOOD", "GENERATED", null, "png", PNG))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("GOOD", "NO_ACTIVATION", "ZERO_MAP", null, null))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "gif", PNG))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, null, PNG))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "png", null))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "png", "not base64!!"))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "png", "aGVsbG8="))).isEqualTo(GradcamStatus.FAILED);
        // 선언과 실제 형식 불일치
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "png", JPEG))).isEqualTo(GradcamStatus.FAILED);
        assertThat(status(new Gradcam("DEFECT", "GENERATED", null, "jpeg", PNG))).isEqualTo(GradcamStatus.FAILED);
    }
}
