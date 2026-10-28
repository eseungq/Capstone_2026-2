package com.capstone.inspection.domain.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, String> {

    @Query("select t from RefreshToken t join fetch t.user where t.tokenHash = :tokenHash")
    Optional<RefreshToken> findByTokenHashWithUser(String tokenHash);
}
