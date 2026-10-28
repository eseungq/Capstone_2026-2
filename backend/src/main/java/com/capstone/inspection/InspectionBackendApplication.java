package com.capstone.inspection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

// 기본 메모리 사용자(임시 비밀번호) 자동 생성은 쓰지 않음 → JWT 인증만 사용
@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
@ConfigurationPropertiesScan // app.* 설정값(AppProperties)을 읽어 옴
public class InspectionBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(InspectionBackendApplication.class, args);
    }
}
