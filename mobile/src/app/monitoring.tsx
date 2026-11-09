
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import MonitoringDashboardV4 from '../components/MonitoringDashboardV4';
import MonitoringLiveDashboardV4 from '../components/MonitoringLiveDashboardV4';
type Tab = 'monitoring' | 'history' | 'settings';

// Figma에서 내려받은 이미지
const doorImage = require('../../assets/images/door_inspection_1.png');
const doorPassImage = require('../../assets/images/door_inspection_2.png');

// 화면 표시용 Mock 데이터 (서버 응답이 아님)
const recentInspections = [
  {
    no: 'INS-008',
    label: '분석 중',
    color: '#2054D8',
    image: doorImage,
  },
  {
    no: 'INS-006',
    label: 'REVIEW',
    color: '#A74B12',
    image: doorImage,
  },
  {
    no: 'INS-002',
    label: 'PASS 예시',
    color: '#067647',
    image: doorPassImage,
  },
];

const mockAlerts = [
  {
    no: 'INS-006',
    state: 'REVIEW',
    description: 'AI 예측: 불량 쪽 · Mock / 작업자 확인 대기',
  },
  {
    no: 'INS-005',
    state: 'REVIEW',
    description: 'AI 예측: 정상 쪽 · Mock / 정책 미충족 · 확인 대기',
  },
  {
    no: 'INS-007',
    state: 'FAILED',
    description: 'AI 분석 시간 초과 · 오류 상세 및 재시도',
  },
];

export default function MonitoringScreen() {
  const router = useRouter();
  const { role, mode } = useLocalSearchParams<{
  role?: string;
  mode?: string;
}>();

const isAdmin = role === 'ADMIN';
const isLive = mode === 'live';

  const [activeTab, setActiveTab] = useState<Tab>('monitoring');

  
const showInspection = (inspectionNo: string) => {
  router.push({
    pathname: '/inspection/[id]',
    params: {
      id: inspectionNo,
      role: isAdmin ? 'ADMIN' : 'WORKER',
    },
  });
};


  const pageTitle =
    activeTab === 'monitoring'
      ? '공정 모니터링'
      : activeTab === 'history'
        ? '검사 이력'
        : '설정';

  const pageSubtitle =
    activeTab === 'monitoring'
      ? isAdmin
        ? '전체 라인·검사·오류 조회 · Mock'
        : '최근 이미지 · 확인 필요 알림 · Mock'
      : activeTab === 'history'
        ? '검사 기록 조회 · Mock'
        : isAdmin
          ? '시스템 관리자 · Mock'
          : '현장 작업자 · Mock';

  return (
    <SafeAreaView style={styles.screen}>
      <Stack.Screen options={{ headerShown: false }} />

      {/* 화면 제목 */}
      <View style={styles.header}>
        <Text style={styles.title}>{pageTitle}</Text>
        <Text style={styles.subtitle}>{pageSubtitle}</Text>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {activeTab === 'monitoring' ? (
          <>
            {/* 73단계: 공정 요약 · 최근 접수 · 대기열 · 새 알림은 하나의 폴링 데이터 출처 공유 */}
            {isLive ? (
  <MonitoringLiveDashboardV4 />
) : (
  <MonitoringDashboardV4 />
)}
{!isLive && (
  <>
            {/* 아래 자료는 예전 로컬 INS Mock 상세 화면을 확인하기 위한 별도 샘플 */}
            <View style={styles.inputCard}>
              <Text style={styles.cardTitle}>기존 로컬 Mock 검사 · 상세 이동</Text>
              <Text style={styles.description}>
                아래 사진과 INS 검사 기록은 상단의 CONTRACT_EXAMPLE 폴링 자료와 별개입니다.
                기존 화면, 저장된 판정 및 품질 통계는 변경하지 않습니다.
              </Text>
            </View>

            <Pressable
              style={styles.doorCard}
              onPress={() => showInspection('INS-008')}
            >
              <Image source={doorImage} style={styles.doorImage} resizeMode="cover" />
              <View style={styles.doorDetails}>
                <Text style={styles.cardTitle}>DOOR · 기존 INS Mock 사진</Text>
                <Text style={styles.description}>INS-008 · 로컬 상세 보기 · 가상 폴링과 별도</Text>
                <View style={styles.analyzingBadge}>
                  <Text style={styles.analyzingText}>분석 중 · 예시</Text>
                </View>
              </View>
            </Pressable>

            <Text style={styles.sectionTitle}>기존 Mock 검사 사진 · 탭하면 상세 이동</Text>
            <View style={styles.thumbnailRow}>
              {recentInspections.map((item) => (
                <Pressable
                  key={item.no}
                  style={styles.thumbnail}
                  onPress={() => showInspection(item.no)}
                >
                  <Image
                    source={item.image}
                    style={styles.thumbnailImage}
                    resizeMode="cover"
                  />
                  <View style={styles.thumbnailLabelArea}>
                    <Text
                      style={[styles.thumbnailLabel, { color: item.color }]}
                      numberOfLines={1}
                      adjustsFontSizeToFit
                      minimumFontScale={0.85}
                    >
                      {item.no} {item.label}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </View>

            <Text style={[styles.sectionTitle, styles.alertTitle]}>
              기존 INS Mock 확인·오류 상세 링크
            </Text>
            {mockAlerts.map((item) => {
              const failed = item.state === 'FAILED';
              return (
                <Pressable
                  key={item.no}
                  style={styles.alertCard}
                  onPress={() => showInspection(item.no)}
                >
                  <View style={styles.alertTop}>
                    <View style={[styles.stateBadge, failed ? styles.failedBadge : styles.reviewBadge]}>
                      <Text style={[styles.stateText, failed ? styles.failedText : styles.reviewText]}>
                        {item.state}
                      </Text>
                    </View>
                    <Text style={styles.alertInspectionNo}>{item.no} · DOOR · 로컬 Mock</Text>
                  </View>
                  <Text style={styles.alertDescription}>{item.description}</Text>
                </Pressable>
              );
                        })}
          </>
        )}
          </>
        ) : activeTab === 'history' ? (
          /* 이력 탭: 다음 단계에서 상세 구현 */
          <View style={styles.placeholderCard}>
            <Text style={styles.cardTitle}>
              검사 이력 · Mock
            </Text>
            <Text style={styles.description}>
              최근 검사 기록을 확인하는 화면입니다.
              상세 검색과 필터는 다음 단계에서 구현합니다.
            </Text>

            {recentInspections.map((item) => (
              <Pressable
                key={item.no}
                style={styles.historyRow}
                onPress={() => showInspection(item.no)}
              >
                <Text style={styles.historyNo}>
                  {item.no}
                </Text>
                <Text style={{ color: item.color, fontSize: 11 }}>
                  {item.label}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : (
          /* 설정 탭: 현재는 계정 정보와 돌아가기만 구현 */
          <View style={styles.placeholderCard}>
            <Text style={styles.cardTitle}>
              계정 및 권한 · Mock
            </Text>
            <Text style={styles.description}>
              현재 시연 역할:
              {isAdmin ? ' 시스템 관리자' : ' 현장 작업자'}
            </Text>

            <Text style={styles.description}>
              {isAdmin
                ? '관리자 정책 관리 기능은 다음 단계에서 구현합니다.'
                : '작업자 설정 기능은 다음 단계에서 구현합니다.'}
            </Text>

            <Pressable
              style={styles.logoutButton}
              onPress={() => router.replace('/')}
            >
              <Text style={styles.logoutText}>
                로그인 화면으로 돌아가기
              </Text>
            </Pressable>
          </View>
        )}
      </ScrollView>

      {/* Figma 하단 내비게이션 */}
      <View style={styles.bottomNav}>
        <Pressable
          style={styles.tab}
          onPress={() => setActiveTab('monitoring')}
        >
          <Text
            style={[
              styles.tabIcon,
              activeTab === 'monitoring' && styles.activeTabText,
            ]}
          >
            ▣
          </Text>
          <Text
            style={[
              styles.tabLabel,
              activeTab === 'monitoring' && styles.activeTabText,
            ]}
          >
            모니터링
          </Text>
        </Pressable>

        <Pressable
          style={styles.tab}
          
onPress={() =>
  router.push({
    pathname: '/history',
    params: {
      role: isAdmin ? 'ADMIN' : 'WORKER',
      mode: isLive ? 'live' : 'mock',
    },
  })
}

        >
          <Text
            style={[
              styles.tabIcon,
              activeTab === 'history' && styles.activeTabText,
            ]}
          >
            ▤
          </Text>
          <Text
            style={[
              styles.tabLabel,
              activeTab === 'history' && styles.activeTabText,
            ]}
          >
            이력
          </Text>
        </Pressable>

        <Pressable
          style={styles.tab}
          
onPress={() =>
  router.push({
    pathname: '/settings',
    params: {
      role: isAdmin ? 'ADMIN' : 'WORKER',
      mode: isLive ? 'live' : 'mock',
    },
  })
}

        >
          <Text
            style={[
              styles.tabIcon,
              activeTab === 'settings' && styles.activeTabText,
            ]}
          >
            ⚙
          </Text>
          <Text
            style={[
              styles.tabLabel,
              activeTab === 'settings' && styles.activeTabText,
            ]}
          >
            설정
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#F5F7FB',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 15,
    paddingBottom: 31,
  },
  title: {
    color: '#111827',
    fontSize: 23,
    fontWeight: '700',
    lineHeight: 34,
  },
  subtitle: {
    color: '#64748B',
    fontSize: 11,
    marginTop: 2,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 24,
  },
  inputCard: {
    backgroundColor: '#EBF1FF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 13,
    gap: 7,
    marginBottom: 8,
  },
  cardTitle: {
    fontSize: 13,
    lineHeight: 21,
    fontWeight: '700',
    color: '#111827',
  },
  description: {
    fontSize: 11,
    lineHeight: 17,
    color: '#64748B',
    flexShrink: 1,
  },
  infoRow: {
    marginTop: 2,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  rowValue: {
    color: '#111827',
    fontSize: 11,
    fontWeight: '500',
    textAlign: 'right',
    flexShrink: 1,
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 23,
    marginBottom: 5,
  },
  recentText: {
    color: '#2054D8',
    fontSize: 11,
    lineHeight: 16,
    marginBottom: 5,
  },
  doorCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    marginBottom: 5,
  },
  doorImage: {
    width: 112,
    height: 70,
    borderRadius: 8,
    backgroundColor: '#EEF2F8',
  },
  doorDetails: {
    flex: 1,
    gap: 5,
    paddingTop: 2,
  },
  analyzingBadge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: '#EBF1FF',
  },
  analyzingText: {
    color: '#A74B12',
    fontSize: 10,
    fontWeight: '500',
  },
  thumbnailRow: {
    flexDirection: 'row',
    gap: 5,
    marginBottom: 7,
  },
  thumbnail: {
    flex: 1,
    minWidth: 0,
    backgroundColor: '#FFFFFF',
  },
  thumbnailImage: {
    width: '100%',
    height: 28,
    borderRadius: 5,
    backgroundColor: '#EEF2F8',
  },
  thumbnailLabelArea: {
    height: 22,
    paddingHorizontal: 3,
    paddingTop: 2,
    justifyContent: 'center',
  },
  thumbnailLabel: {
    fontSize: 11,
    lineHeight: 16,
  },
  alertTitle: {
    marginBottom: 5,
  },
  alertCard: {
    minHeight: 73,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 13,
    padding: 12,
    gap: 6,
    marginBottom: 5,
  },
  alertTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stateBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  reviewBadge: {
    backgroundColor: '#FFF3E5',
  },
  failedBadge: {
    backgroundColor: '#FFF0ED',
  },
  stateText: {
    fontSize: 10,
    lineHeight: 15,
    fontWeight: '500',
  },
  reviewText: {
    color: '#A74B12',
  },
  failedText: {
    color: '#B42318',
  },
  alertInspectionNo: {
    color: '#111827',
    fontSize: 12,
    fontWeight: '700',
  },
  alertDescription: {
    color: '#64748B',
    fontSize: 11,
    lineHeight: 16,
    flexShrink: 1,
  },
  bottomNav: {
    flexDirection: 'row',
    height: 58,
    marginHorizontal: 20,
    marginBottom: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 15,
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  tab: {
    flex: 1,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  tabIcon: {
    fontSize: 19,
    lineHeight: 24,
    color: '#64748B',
  },
  tabLabel: {
    fontSize: 11,
    lineHeight: 16,
    color: '#64748B',
    fontWeight: '500',
  },
  activeTabText: {
    color: '#2054D8',
    fontWeight: '700',
  },
  placeholderCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 15,
    gap: 12,
  },
  historyRow: {
    borderTopWidth: 1,
    borderTopColor: '#E4E7EC',
    paddingVertical: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  historyNo: {
    fontSize: 12,
    fontWeight: '600',
    color: '#111827',
  },
  logoutButton: {
    backgroundColor: '#2054D8',
    padding: 13,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  logoutText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
});
