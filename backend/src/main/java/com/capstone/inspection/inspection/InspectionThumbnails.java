package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.storage.ImageUrlSigner;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.Collection;
import java.util.Map;
import java.util.stream.Collectors;

// 목록용 썸네일 주소. 썸네일을 따로 만들지 않고 원본의 서명 주소를 사용 (만료되면 목록을 다시 조회)
// 여러 검사의 원본을 쿼리 1번으로 조회
@Component
@RequiredArgsConstructor
public class InspectionThumbnails {

    private final ImageStorageRepository imageRepository;
    private final ImageUrlSigner signer;

    // 검사 ID → 원본 서명 주소 (원본이 없는 검사는 빠짐)
    public Map<String, String> urlsFor(Collection<Inspection> inspections) {
        if (inspections.isEmpty()) {
            return Map.of();
        }
        var ids = inspections.stream().map(Inspection::getId).toList();
        return imageRepository.findByInspectionIdsAndType(ids, ImageType.ORIGINAL).stream()
                .collect(Collectors.toMap(s -> s.getInspection().getId(), this::sign, (a, b) -> a));
    }

    private String sign(ImageStorage s) {
        return signer.sign(s.getId()).url();
    }
}
