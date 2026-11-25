import React,{useCallback,useRef,useState} from 'react';
import {router,Stack,useFocusEffect} from 'expo-router';
import {ActivityIndicator,KeyboardAvoidingView,Platform,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {authV4} from '../api/backendV4/authRuntime';
import {createDailyHistoryServiceV4} from '../api/backendV4/adminDailyHistoryServiceV4';
import {
 dailyAiReviewRateV4,kstCalendarTodayV4,oppositeEvidenceTextV4,plusDaysV4,
 type AutomationDailyPartV4,type DailyHistoryRowV4,type DailyDetailV4,
 type DailyBandV4,
} from '../api/backendV4/adminDailyHistoryCoreV4';
import {createDailyHistoryReadsV4,idleDailyRead,type DailyReadState} from '../components/adminDailyHistoryReadsV4';

const service=createDailyHistoryServiceV4(authV4);
const parts:AutomationDailyPartV4[]=['DOOR','FRAME','COWL_COVER'];
const ink='#111827',blue='#2054D8',muted='#475569',red='#B42318';
function fraction(value:number|null,digits=2):string{
 return value==null?'미제공':`${(value*100).toFixed(digits)}%`;
}
function Line({label,value}:{label:string;value:string}){
 return <View style={s.line}><Text style={s.lineLabel}>{label}</Text><Text style={s.lineValue}>{value}</Text></View>;
}
function Band({title,band,onOpen}:{title:string;band:DailyBandV4|null;onOpen:(id:string)=>void}){
 return <View style={s.band}>
   <Text style={s.strong}>{title}</Text>
   {!band?<Text style={s.muted}>해당 기준 또는 구간 자료 없음</Text>:<>
     <Text style={s.muted}>
       범위: {fraction(band.from,4)} ~ {fraction(band.to,4)}
     </Text>
     <Line label="구간 전체" value={`${band.total}건`}/>
     <Line label="작업자 통과 / 불량 / 미판정" value={`${band.pass} / ${band.fail} / ${band.pending}건`}/>
     {band.items.map(item=><Pressable key={item.inspectionId}
       accessibilityRole="button" onPress={()=>onOpen(item.inspectionId)}
       style={s.item}>
       <Text style={s.strong}>{item.inspectionNo} · {fraction(item.calibratedDefectProbability,4)}</Text>
       <Text style={s.muted}>최초: {item.finalJudgement??'미판정'}
         {item.correctedJudgement? ` · 정정: ${item.correctedJudgement}`:''}</Text>
       <Text style={s.link}>검사 상세 확인 ›</Text>
     </Pressable>)}
     {band.items.length===0&&<Text style={s.muted}>이 구간에는 작업자 확인 대상 검사가 없습니다.</Text>}
   </>}
 </View>;
}
function DailyRowCard({row,onViewDetail,children}:{row:DailyHistoryRowV4;onViewDetail:()=>void;children?:React.ReactNode}){
 const [expanded,setExpanded]=useState(false);
 const rate=dailyAiReviewRateV4(row);
 return <View style={s.history}>
   <Text style={s.strong}>{row.date} · {row.policyVersion??'정책 없음'}</Text>
   <View style={s.totalRow}>
     <Text style={s.strong}>전체 검사</Text>
     <Text style={s.totalValue}>{row.total}건</Text>
   </View>
   <View style={s.metrics}>
     <View style={s.metric}>
       <Text style={s.metricLabel}>자동 통과</Text>
       <Text style={[s.metricValue,s.passValue]}>{row.autoPass}건</Text>
     </View>
     <View style={s.metric}>
       <Text style={s.metricLabel}>자동 불량</Text>
       <Text style={[s.metricValue,s.failValue]}>{row.autoFail}건</Text>
     </View>
     <View style={s.metric}>
       <Text style={s.metricLabel}>작업자 확인</Text>
       <Text style={s.metricValue}>{row.review.total}건</Text>
     </View>
   </View>
   <Line label="작업자 판정 완료" value={`${row.review.done}/${row.review.total}건`}/>
   <Line label="수동 전환 (작업자 확인에 포함)" value={`${row.manual.done}/${row.manual.total}건`}/>
   <Line label="AI 분석 실패 (집계 제외)" value={`${row.failed}건`}/>
   <Line label="판정 확인 근거" value={oppositeEvidenceTextV4(row)}/>
   <Line label="처리 대기 확인 요청" value={`${row.openRequests}건`}/>
   <Pressable style={s.detailsToggle} accessibilityRole="button" accessibilityState={{expanded}}
     onPress={()=>setExpanded(value=>!value)}>
     <Text style={s.link}>{expanded?'세부 통계 접기':'세부 통계 보기'}</Text>
     <Text style={s.link}>{expanded?'−':'+'}</Text>
   </Pressable>
   {expanded&&<View style={s.detailStats}>
     <Text style={s.muted}>모델 {row.modelVersion??'미제공'} · 보정기 {row.calibratorVersion??'미제공'}</Text>
     <Line label="AI 검사 중 작업자 확인 비율 (수동 제외)" value={rate===null?'산출 불가':fraction(rate)}/>
     <Line label="자동 불량 설정" value={row.autoFailEnabled?'켜짐':'꺼짐'}/>
     <Line label="자동 통과 / 불량 기준" value={`${fraction(row.passThreshold,4)} / ${fraction(row.failThreshold,4)}`}/>
     <Line label="자동 통과→불량 / 자동 불량→통과" value={`${row.confirmedOpposite.autoPassThenFail} / ${row.confirmedOpposite.autoFailThenPass}건`}/>
   </View>}
   {row.policyId?<Pressable style={s.outline} accessibilityRole="button"
     onPress={onViewDetail}><Text style={s.link}>기준 주변의 작업자 확인 검사 보기 ›</Text></Pressable>
     :<Text style={s.muted}>정책 없음: 기준 주변 상세 없음</Text>}
   {children}
 </View>;
}
export default function AdminDailyLiveScreen(){
 const today=kstCalendarTodayV4();
 const [part,setPart]=useState<AutomationDailyPartV4>('COWL_COVER');
 const [from,setFrom]=useState(plusDaysV4(today,-6));
 const [to,setTo]=useState(plusDaysV4(today,1));
 const [band,setBand]=useState('0.05');
 const [access,setAccess]=useState<'checking'|'admin'|'denied'>('checking');
 const [listState,setListState]=useState<DailyReadState<DailyHistoryRowV4[]>>(idleDailyRead);
 const [detailState,setDetailState]=useState<DailyReadState<DailyDetailV4>>(idleDailyRead);
 const [selected,setSelected]=useState<DailyHistoryRowV4|null>(null);
 const [reads]=useState(()=>createDailyHistoryReadsV4(service,setListState,setDetailState));
 const {value:rows,loading,error}=listState;
 const {value:detail,loading:detailLoading,error:detailError}=detailState;

 const clearResults=useCallback(()=>{
   reads.reset();
   setSelected(null);
 },[reads]);
 const load=useCallback(()=>{
   setSelected(null);
   return reads.loadRows(part,from,to);
 },[reads,part,from,to]);
 const loadRef=useRef(load);
 loadRef.current=load;
 useFocusEffect(useCallback(()=>{
   let active=true;
   void authV4.restore().then(session=>{
     if(!active)return;
     const authorized=session.signedIn&&session.role==='ADMIN';
     setAccess(authorized?'admin':'denied');
     if(authorized)void loadRef.current();
   }).catch(()=>{if(active)setAccess('denied');});
   return()=>{
     active=false;
     clearResults();
     setAccess('checking');
   };
 },[clearResults]));
 const viewDetail=(row:DailyHistoryRowV4)=>{
   if(!row.policyId)return;
   setSelected(row);
   return reads.loadDetail(part,row.date,row.policyId,band);
 };
 const openInspection=(id:string)=>router.push({pathname:'/inspection-live',params:{inspectionId:id}});
 return <SafeAreaView style={s.root}>
   <Stack.Screen options={{headerShown:false}}/>
   <View style={s.header}>
     <Pressable accessibilityRole="button" onPress={()=>router.back()} style={s.backTouch}>
       <Text style={s.link}>‹ 뒤로</Text>
     </Pressable>
     <Text style={s.title}>날짜별 자동 판정 이력</Text>
     <Text style={s.muted}>관리자 · 한국 시간 기준</Text>
   </View>
   <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
   <ScrollView style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
     {access==='checking'&&<ActivityIndicator/>}
     {access==='denied'&&<View style={s.card}>
       <Text style={s.error}>날짜별 자동 판정 이력은 관리자 계정에서 조회할 수 있습니다.</Text>
     </View>}
     {access==='admin'&&<>
       <View style={s.card}>
         <Text style={s.strong}>부품 선택</Text>
         <View style={s.chips}>{parts.map(p=><Pressable key={p} accessibilityRole="button"
           accessibilityState={{selected:part===p}}
           onPress={()=>{if(p!==part){clearResults();setPart(p);}}} style={[s.chip,part===p&&s.chipActive]}>
           <Text style={[s.chipText,part===p&&s.chipTextActive]}>{p}</Text>
         </Pressable>)}</View>
         <Text style={s.strong}>접수 날짜 범위 (서울 기준 · 시작 포함 / 종료 제외)</Text>
         <Text style={s.muted}>YYYY-MM-DD · 최대 92일. 오늘까지 포함하려면 종료일을 내일로 설정하세요.</Text>
         <View style={s.chips}>
           <View style={s.dateCell}><Text style={s.muted}>시작일</Text>
             <TextInput testID="daily-start-date" accessibilityLabel="접수 시작일" value={from} onChangeText={x=>{clearResults();setFrom(x);}} style={s.input} autoCorrect={false}
               placeholder="YYYY-MM-DD" maxLength={10}/></View>
           <View style={s.dateCell}><Text style={s.muted}>종료일 (미포함)</Text>
             <TextInput testID="daily-end-exclusive-date" accessibilityLabel="접수 종료일 (미포함)" value={to} onChangeText={x=>{clearResults();setTo(x);}} style={s.input} autoCorrect={false}
               placeholder="YYYY-MM-DD" maxLength={10}/></View>
         </View>
         <Pressable style={s.primary} accessibilityRole="button" disabled={loading}
           onPress={()=>{void load();}}>
           <Text style={s.primaryText}>{loading?'조회 중…':'날짜별 통계 조회'}</Text>
         </Pressable>
         <Text style={s.muted}>검사 접수 날짜와 당시 적용한 정책·모델·보정기별로 집계합니다.</Text>
       </View>
       {loading&&<ActivityIndicator/>}
       {error&&<View style={s.card}><Text style={s.error}>{error}</Text></View>}
       {rows!==null&&<View style={s.card}>
         <Text style={s.strong}>날짜·정책별 결과 · {rows.length}행</Text>
         {rows.length===0&&<Text style={s.muted}>선택한 부품은 이 기간에 집계된 검사가 없습니다. 다른 기간이나 부품을 선택해 주세요.</Text>}
         {rows.map((row,index)=>(
           <DailyRowCard key={row.date+'|'+(row.policyId??'')+'|'+(row.modelVersion??'')+'|'+(row.calibratorVersion??'')+'|'+index}
             row={row} onViewDetail={()=>{void viewDetail(row);}}>
       {selected===row&&<View style={s.detailCard}>
         <Text style={s.strong}>기준 상세 · {selected.date} · {selected.policyVersion??'정책 없음'}</Text>
         <Text style={s.muted}>구간 폭은 확률 차이입니다. 0.05를 입력하면 기준에서 5%p 이내의 검사를 조회합니다. 입력 범위는 0.001~0.5입니다.</Text>
         <TextInput testID="daily-threshold-band" accessibilityLabel="기준 주변 확률 구간 폭" value={band} onChangeText={x=>{reads.resetDetail();setBand(x);}} style={s.input}
           keyboardType="decimal-pad" placeholder="0.05" />
         <Pressable style={s.outline} accessibilityRole="button" disabled={detailLoading}
           onPress={()=>{void viewDetail(selected);}}>
           <Text style={s.link}>{detailLoading?'조회 중…':'선택한 날짜·정책 구간 다시 조회'}</Text>
         </Pressable>
         {detailLoading&&<ActivityIndicator/>}
         {detailError&&<Text style={s.error}>{detailError}</Text>}
         {detail&&<>
           <Line label="정책/기준" value={`${detail.policyVersion} · ${fraction(detail.passThreshold,4)} / ${fraction(detail.failThreshold,4)}`}/>
           <Line label="실물 판정 참고 자료" value={detail.reference===null?'자료 없음':'자료 확인'}/>
           <Band title="통과 기준 바로 위 · AI 정상 예측" band={detail.passBand} onOpen={openInspection}/>
           <Band title="불량 기준 바로 아래 · AI 불량 예측" band={detail.failBand} onOpen={openInspection}/>
         </>}
       </View>}
           </DailyRowCard>
         ))}
       </View>}
       <Text style={s.muted}>통계의 '판정 완료'는 조회 시점 기준입니다. 정책 변경이 과거 검사를 소급 변경하지 않습니다. 집계의 ‘확인 자료 없음’은 관리자가 유지 또는 정정 처리한 검사가 0건이라는 뜻입니다. 기준 상세의 ‘자료 없음’은 실물 판정 참고 자료가 없다는 뜻입니다. 실물 기준으로 확인한 자료가 있어야 품질 정확도나 미검출률을 평가할 수 있습니다.</Text>
     </>}
   </ScrollView>
   </KeyboardAvoidingView>
 </SafeAreaView>;
}
const s=StyleSheet.create({
  backTouch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
 root:{flex:1,backgroundColor:'#F5F7FB'},header:{padding:18,gap:8},scroll:{flex:1},
 body:{paddingHorizontal:18,paddingBottom:35,gap:12},title:{fontSize:22,fontWeight:'700',color:ink},
 strong:{fontSize: 14,fontWeight:'700',color:ink},muted:{color:muted,fontSize: 13,lineHeight:18},
 card:{backgroundColor:'#FFF',borderRadius:14,borderColor:'#E4E7EC',borderWidth:1,padding:14,gap:12},
 chips:{flexDirection:'row',flexWrap:'wrap',gap:6},chip:{ justifyContent: 'center', minHeight: 44,borderWidth:1,borderRadius:9,borderColor:'#64748B',padding:9},
 chipActive:{backgroundColor:'#1E293B',borderColor:'#1E293B'},chipText:{fontSize: 13,fontWeight:'700',color:'#334155'},
 chipTextActive:{color:'#FFF'},dateCell:{flex:1,minWidth:124,gap:6},
 input:{ minHeight: 44,borderWidth:1,borderColor:'#64748B',borderRadius:9,padding:11,fontSize: 14,color:ink},
 primary:{ justifyContent: 'center', minHeight: 44,backgroundColor:blue,padding:13,borderRadius:10,alignItems:'center'},
 primaryText:{color:'#FFF',fontWeight:'700',fontSize: 14},
 outline:{ justifyContent: 'center', minHeight: 44,borderWidth:1,borderColor:blue,borderRadius:10,padding:10,alignItems:'center'},
 link:{color:blue,fontSize: 13,fontWeight:'700'},error:{color:red,fontSize:12,lineHeight:20},
 line:{flexDirection:'row',alignItems:'flex-start',justifyContent:'space-between',gap:10},
 lineLabel:{flex:0.56,color:muted,fontSize: 13,lineHeight: 18},
 lineValue:{flex:0.44,color:ink,fontSize: 13,fontWeight:'600',textAlign:'right',lineHeight: 18},
 history:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingVertical:12,gap:8},
 totalRow:{flexDirection:'row',alignItems:'baseline',justifyContent:'space-between',gap:8},
 totalValue:{color:ink,fontSize:22,fontWeight:'700',flexShrink:1},
 metrics:{flexDirection:'row',gap:6},
 metric:{flex:1,minWidth:0,backgroundColor:'#F5F7FB',borderRadius:9,padding:8,gap:4},
 metricLabel:{color:muted,fontSize:12,lineHeight:17},
 metricValue:{color:ink,fontSize:18,fontWeight:'700'},
 passValue:{color:'#067647'},failValue:{color:red},
 detailsToggle:{minHeight:44,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8,paddingHorizontal:4},
 detailStats:{backgroundColor:'#F8FAFC',borderRadius:9,padding:10,gap:8},
 detailCard:{backgroundColor:'#F8FAFC',borderWidth:1,borderColor:'#E4E7EC',borderRadius:10,padding:10,gap:10},
 band:{backgroundColor:'#F8FAFC',padding:12,borderRadius:10,gap:9},
 item:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingTop:9,gap:4},
});
