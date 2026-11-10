package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.UserLockResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.user.User;
import com.capstone.inspection.domain.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 계정 잠금 해제 (TBD-10: 로그인 5회 실패 잠금, 관리자 해제)
@Service
@RequiredArgsConstructor
public class AdminUserService {

    private final UserRepository userRepository;

    // 잠기지 않은 계정도 실패 횟수만 초기화하고 성공으로 응답
    @Transactional
    public UserLockResponse unlock(String loginId) {
        User user = userRepository.findByLoginId(loginId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.unlock();
        return new UserLockResponse(user.getLoginId(), user.isLocked(), user.getFailedLoginCount());
    }
}
