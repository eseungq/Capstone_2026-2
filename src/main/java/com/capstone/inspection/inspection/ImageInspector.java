package com.capstone.inspection.inspection;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.Iterator;

// 이미지 형식·크기 확인. 전체를 디코딩하지 않고 헤더만 읽음
public final class ImageInspector {

    public record ImageInfo(String contentType, String extension, int width, int height) {
    }

    private ImageInspector() {
    }

    // JPEG·PNG가 아니거나 읽을 수 없으면 null
    public static ImageInfo inspect(byte[] bytes) {
        try (ImageInputStream in = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            if (in == null) {
                return null;
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(in);
            if (!readers.hasNext()) {
                return null;
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(in);
                String format = reader.getFormatName().toLowerCase();
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (format.equals("jpeg") || format.equals("jpg")) {
                    return new ImageInfo("image/jpeg", "jpg", width, height);
                }
                if (format.equals("png")) {
                    return new ImageInfo("image/png", "png", width, height);
                }
                return null;
            } finally {
                reader.dispose();
            }
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }
}
