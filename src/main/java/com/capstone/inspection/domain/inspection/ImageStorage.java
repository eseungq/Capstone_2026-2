package com.capstone.inspection.domain.inspection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.UUID;

// 검사 이미지 1건 (원본 또는 Grad-CAM). 검사당 원본 1, Grad-CAM 최대 1
@Entity
@Table(name = "image_storage")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ImageStorage {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inspection_id")
    private Inspection inspection;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private ImageType imageType;

    @Column(nullable = false, length = 500)
    private String storageUri;   // 저장소 상대 키 (예: original/2026/10/16/<id>.jpg). 저장소 종류는 TBD-01

    @Column(nullable = false, length = 50)
    private String contentType;  // image/jpeg 등

    @Column(nullable = false)
    private long sizeBytes;

    @Column(nullable = false)
    private int width;           // 방향 보정 처리 지점 확정 전까지는 파일 그대로의 크기 (TBD-09)

    @Column(nullable = false)
    private int height;

    @Column(nullable = false, length = 64)
    private String checksum;     // SHA-256 (원본 무결성 확인, Idempotency 비교)

    private Integer exifOrientation;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    public ImageStorage(Inspection inspection, ImageType imageType, String storageUri, String contentType,
                        long sizeBytes, int width, int height, String checksum) {
        this.id = UUID.randomUUID().toString();
        this.inspection = inspection;
        this.imageType = imageType;
        this.storageUri = storageUri;
        this.contentType = contentType;
        this.sizeBytes = sizeBytes;
        this.width = width;
        this.height = height;
        this.checksum = checksum;
        this.createdAt = LocalDateTime.now();
    }
}
