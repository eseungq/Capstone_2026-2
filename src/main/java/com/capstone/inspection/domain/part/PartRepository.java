package com.capstone.inspection.domain.part;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface PartRepository extends JpaRepository<Part, String> {

    Optional<Part> findByPartCode(String partCode);
}
