package com.capstone.inspection.part.dto;

import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.Part;

import java.util.List;
import java.util.Map;
import java.util.Set;

// GET /api/v1/parts 응답의 부품 1개 (FR-BE-03)
public record PartResponse(String partCode, String name, List<ItemResponse> items) {

    // 검사항목 1개와 활성 모델 상태
    public record ItemResponse(String inspectionItemCode,
                               String name,
                               boolean modelAvailable,      // 활성 모델 있음 + AI 서버 로드 확인됨
                               boolean policyActive,        // 활성 모델에 ready·active 정책 있음
                               String activeModelVersion) { // 활성 모델 버전, 없으면 null
    }

    public static PartResponse of(Part part, List<InspectionItem> items, Map<String, AiModel> activeModelByItemId,
                                  Set<String> availableModelIds, Set<String> itemsWithPolicy) {
        List<ItemResponse> itemResponses = items.stream()
                .map(item -> {
                    AiModel model = activeModelByItemId.get(item.getId()); // 이 항목의 활성 모델
                    return new ItemResponse(
                            item.getItemCode(),
                            item.getName(),
                            model != null && availableModelIds.contains(model.getId()),
                            itemsWithPolicy.contains(item.getId()),
                            model != null ? model.getModelVersion() : null);
                })
                .toList();
        return new PartResponse(part.getPartCode(), part.getName(), itemResponses);
    }
}
