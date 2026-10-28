package com.capstone.inspection.storage;

import com.capstone.inspection.config.AppProperties;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

// 개발용 로컬 디스크 저장소 (app.storage.local-root 아래에 저장)
@Service
public class LocalStorageService implements StorageService {

    private final Path root;

    public LocalStorageService(AppProperties props) {
        this.root = Path.of(props.storage().localRoot()).toAbsolutePath().normalize();
    }

    @Override
    public void save(String key, byte[] bytes) throws IOException {
        Path target = resolve(key);
        Files.createDirectories(target.getParent());
        // 임시 파일에 쓴 뒤 이동해서, 쓰는 도중의 파일을 다른 요청이 읽지 않도록 함
        Path tmp = Files.createTempFile(target.getParent(), ".upload-", ".tmp");
        try {
            Files.write(tmp, bytes);
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    @Override
    public byte[] read(String key) throws IOException {
        return Files.readAllBytes(resolve(key));
    }

    @Override
    public boolean exists(String key) {
        return Files.isRegularFile(resolve(key));
    }

    // 키에 ../ 등이 들어와 저장소 밖을 가리키지 않도록 확인
    private Path resolve(String key) {
        Path p = root.resolve(key).normalize();
        if (!p.startsWith(root)) {
            throw new IllegalArgumentException("invalid storage key");
        }
        return p;
    }
}
