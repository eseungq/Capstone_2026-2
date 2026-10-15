package com.capstone.inspection.storage;

import java.io.IOException;

// 이미지 저장소. 키는 저장소 상대 경로 (예: original/2026/10/16/<id>.jpg). 로컬·S3 결정은 TBD-01
public interface StorageService {

    void save(String key, byte[] bytes) throws IOException;

    byte[] read(String key) throws IOException;

    boolean exists(String key);
}
