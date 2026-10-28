package com.capstone.inspection.part.dto;

import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.Part;

import java.util.List;
import java.util.Map;

// GET /api/v1/parts 응답의 부품 1개 (FR-BE-03)
public record PartResponse(String partCode, String name, List<ItemResponse> items) {

    // 검사항목 1개와 활성 모델 상태
    public record ItemResponse(String inspectionItemCode,
                               String name,
                               boolean modelAvailable,            // 활성 모델 존재 여부 (AI 서버 로드 확인은 이후 단계에서 추가)
                               boolean patchInspectionSupported,  // 활성 모델의 패치 검사 제공 여부
                               String activeModelVersion) {       // 활성 모델 버전, 없으면 null
    }

    public static PartResponse of(Part part, List<InspectionItem> items, Map<String, AiModel> activeModelByItemId) {
        List<ItemResponse> itemResponses = items.stream()
                .map(item -> {
                    AiModel model = activeModelByItemId.get(item.getId()); // 이 항목의 활성 모델
                    return new ItemResponse(
                            item.getItemCode(),
                            item.getName(),
                            model != null,
                            model != null && model.isPatchInspectionSupported(),
                            model != null ? model.getModelVersion() : null);
                })
                .toList();
        return new PartResponse(part.getPartCode(), part.getName(), itemResponses);
    }
}
