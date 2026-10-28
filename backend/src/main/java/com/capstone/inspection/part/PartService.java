package com.capstone.inspection.part;

import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.InspectionItemRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.part.dto.PartResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PartService {

    private final PartRepository partRepository;
    private final InspectionItemRepository itemRepository;
    private final AiModelRepository aiModelRepository;

    // 부품 → 검사항목 → 활성 모델 상태를 묶어서 반환
    public List<PartResponse> getParts() {
        List<Part> parts = partRepository.findAll(Sort.by("partCode"));

        // 부품 ID별 검사항목 목록
        Map<String, List<InspectionItem>> itemsByPartId = itemRepository.findAllWithPart().stream()
                .collect(Collectors.groupingBy(item -> item.getPart().getId()));

        // 검사항목 ID별 활성 모델 (항목당 1개가 원칙, 중복 시 첫 번째 사용)
        Map<String, AiModel> activeModelByItemId = aiModelRepository.findAllActiveWithItem().stream()
                .collect(Collectors.toMap(m -> m.getItem().getId(), Function.identity(), (a, b) -> a));

        return parts.stream()
                .map(p -> PartResponse.of(p, itemsByPartId.getOrDefault(p.getId(), List.of()), activeModelByItemId))
                .toList();
    }
}
