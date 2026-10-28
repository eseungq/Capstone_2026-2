package com.capstone.inspection.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    private static final String BEARER = "bearerAuth";

    // Swagger UI(/swagger-ui.html) 상단 문서 정보 + Authorize 버튼(Access Token 입력)
    @Bean
    public OpenAPI openAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("자동차 부품 품질검사 플랫폼 백엔드 API")
                        .version("v1")
                        .description("3조 김이홍 프로토타입 (계약 v4)"))
                .components(new Components().addSecuritySchemes(BEARER,
                        new SecurityScheme().type(SecurityScheme.Type.HTTP).scheme("bearer").bearerFormat("JWT")))
                .addSecurityItem(new SecurityRequirement().addList(BEARER));
    }
}
