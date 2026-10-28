package com.capstone.inspection.domain.inspection;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

// 화면 표시용 검사 번호 발급 (INS-000001). 카운터 행을 갱신하는 순간 행 잠금이 걸려 동시 접수에도 번호가 겹치지 않음
// 접수 트랜잭션이 롤백되면 번호도 함께 롤백됨
@Component
public class InspectionNoGenerator {

    private static final String SEQ_NAME = "INSPECTION";

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.MANDATORY)
    public String next() {
        em.createNativeQuery("UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = :name")
                .setParameter("name", SEQ_NAME)
                .executeUpdate();
        Number value = (Number) em.createNativeQuery("SELECT last_val FROM inspection_no_seq WHERE name = :name")
                .setParameter("name", SEQ_NAME)
                .getSingleResult();
        return String.format("INS-%06d", value.longValue());
    }
}
