package com.capstone.inspection.storage;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;

@Tag(name = "이미지", description = "서명된 만료 주소로 원본·Grad-CAM 이미지 제공 (토큰 불필요)")
@RestController
@RequiredArgsConstructor
public class ImageController {

    private final ImageUrlSigner signer;
    private final ImageStorageRepository imageRepository;
    private final StorageService storageService;

    @Operation(summary = "이미지 읽기", description = "검사 상세·AI 요청에 들어 있는 주소 그대로 사용. 만료되면 상세를 다시 조회")
    @GetMapping("/api/v1/images/{imageId}")
    public ResponseEntity<byte[]> getImage(@PathVariable String imageId,
                                           @RequestParam long exp,
                                           @RequestParam String sig) {
        if (!signer.verify(imageId, exp, sig)) {
            throw new BusinessException(ErrorCode.IMAGE_NOT_AVAILABLE);
        }
        ImageStorage image = imageRepository.findById(imageId)
                .orElseThrow(() -> new BusinessException(ErrorCode.IMAGE_NOT_AVAILABLE));
        try {
            byte[] bytes = storageService.read(image.getStorageUri());
            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(image.getContentType()))
                    .cacheControl(CacheControl.noStore())
                    .body(bytes);
        } catch (IOException e) {
            throw new BusinessException(ErrorCode.IMAGE_NOT_AVAILABLE);
        }
    }
}
