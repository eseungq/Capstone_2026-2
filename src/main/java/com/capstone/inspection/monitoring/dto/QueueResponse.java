package com.capstone.inspection.monitoring.dto;

import java.util.List;

// GET /monitoring/queue 응답. nextCursor가 null이면 마지막 페이지
public record QueueResponse(List<QueueItem> items, String nextCursor) {
}
