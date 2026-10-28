package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// 계약 v4 7.2 응답 규칙
class AiResponseValidatorTest {

    private static final String ID = "insp-1";
    private static final String MODEL = "mock-door-swin-t-v1";

    private static AiPredictResponse response(String quality, Double raw, Double cal, String calVer) {
        return new AiPredictResponse(ID, MODEL, quality, raw, cal, calVer, 3024, 4032, null, 412);
    }

    private static void assertInvalid(AiPredictResponse r) {
        assertThatThrownBy(() -> AiResponseValidator.validate(r, ID, MODEL))
                .isInstanceOf(AiCallException.class)
                .extracting(e -> ((AiCallException) e).getErrorCode())
                .isEqualTo(ErrorCode.AI_RESPONSE_INVALID);
    }

    @Test
    void validGoodWithoutCalibration() {
        assertThat(AiResponseValidator.validate(response("GOOD", 0.23, null, null), ID, MODEL))
                .isEqualTo(PredictedQuality.GOOD);
    }

    @Test
    void validDefectWithCalibration() {
        assertThat(AiResponseValidator.validate(response("DEFECT", 0.91, 0.88, "cal-v1"), ID, MODEL))
                .isEqualTo(PredictedQuality.DEFECT);
    }

    @Test
    void qualityMustMatchRawScoreAtHalf() {
        assertInvalid(response("GOOD", 0.5, null, null));      // 0.5 이상은 DEFECT
        assertInvalid(response("DEFECT", 0.49, null, null));
    }

    @Test
    void calibratorVersionRequiredWithCalibratedProbability() {
        assertInvalid(response("GOOD", 0.1, 0.02, null));
        assertInvalid(response("GOOD", 0.1, null, "cal-v1"));
    }

    @Test
    void probabilityRange() {
        assertInvalid(response("GOOD", -0.1, null, null));
        assertInvalid(response("DEFECT", 1.2, null, null));
        assertInvalid(response("GOOD", Double.NaN, null, null));
        assertInvalid(response("GOOD", null, null, null));
    }

    @Test
    void identityChecks() {
        assertInvalid(new AiPredictResponse("other", MODEL, "GOOD", 0.1, null, null, 1, 1, null, 1));
        assertInvalid(new AiPredictResponse(ID, "other-model", "GOOD", 0.1, null, null, 1, 1, null, 1));
        assertInvalid(new AiPredictResponse(ID, MODEL, "MAYBE", 0.1, null, null, 1, 1, null, 1));
        assertInvalid(new AiPredictResponse(ID, MODEL, "GOOD", 0.1, null, null, null, 1, null, 1));
        assertInvalid(new AiPredictResponse(ID, MODEL, "GOOD", 0.1, null, null, 1, 1, null, null));
    }
}
