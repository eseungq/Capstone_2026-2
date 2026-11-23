import React,{useCallback,useEffect,useRef,useState} from 'react';
import {router,Stack,useFocusEffect} from 'expo-router';
import {ActivityIndicator,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {authV4} from '../api/backendV4/authRuntime';
import {createDailyHistoryServiceV4} from '../api/backendV4/adminDailyHistoryServiceV4';
import {
 dailyAiReviewRateV4,kstCalendarTodayV4,oppositeEvidenceTextV4,plusDaysV4,
 validateDailyRangeV4,validateDailyBandV4,
 type AutomationDailyPartV4,type DailyHistoryRowV4,type DailyDetailV4,
 type DailyBandV4,
} from '../api/backendV4/adminDailyHistoryCoreV4';

const service=createDailyHistoryServiceV4(authV4);
const parts:AutomationDailyPartV4[]=['DOOR','FRAME','COWL_COVER'];
const ink='#111827',blue='#2054D8',muted='#64748B',red='#B42318';
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
     <Line label="작업자 PASS / FAIL / 미판정" value={`${band.pass} / ${band.fail} / ${band.pending}건`}/>
     {band.items.map(item=><Pressable key={item.inspectionId}
       accessibilityRole="button" onPress={()=>onOpen(item.inspectionId)}
       style={s.item}>
       <Text style={s.strong}>{item.inspectionNo} · {fraction(item.calibratedDefectProbability,4)}</Text>
       <Text style={s.muted}>최초: {item.finalJudgement??'미판정'}
         {item.correctedJudgement? ` · 정정: ${item.correctedJudgement}`:''}</Text>
       <Text style={s.link}>검사 상세 확인 ›</Text>
     </Pressable>)}
     {band.items.length===0&&<Text style={s.muted}>이 구간에 REVIEW 검사가 없습니다.</Text>}
   </>}
 </View>;
}
export default function AdminDailyLiveScreen(){
 const today=kstCalendarTodayV4();
 const [part,setPart]=useState<AutomationDailyPartV4>('COWL_COVER');
 const [from,setFrom]=useState(plusDaysV4(today,-6));
 const [to,setTo]=useState(plusDaysV4(today,1));
 const [band,setBand]=useState('0.05');
 const [access,setAccess]=useState<'checking'|'admin'|'denied'>('checking');
 const [rows,setRows]=useState<DailyHistoryRowV4[]|null>(null);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState<string|null>(null);
 const [selected,setSelected]=useState<DailyHistoryRowV4|null>(null);
 const [detail,setDetail]=useState<DailyDetailV4|null>(null);
 const [detailLoading,setDetailLoading]=useState(false);
 const [detailError,setDetailError]=useState<string|null>(null);
 const serial=useRef(0),detailSerial=useRef(0);

 const load=useCallback(async()=>{
   const current=++serial.current;
   detailSerial.current++;
   setSelected(null);setDetail(null);setDetailError(null);
   setLoading(true);setError(null);setRows(null);
   try{
     validateDailyRangeV4(part,from,to);
     const result=await service.daily(part,from,to);
     if(current===serial.current)setRows(result);
   }catch(e){if(current===serial.current)setError(e instanceof Error?e.message:'서버 통계 조회 실패');}
   finally{if(current===serial.current)setLoading(false);}
 },[part,from,to]);
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
   return()=>{active=false;serial.current++;detailSerial.current++;};
 },[]));
 const viewDetail=async(row:DailyHistoryRowV4)=>{
   const current=++detailSerial.current;
   setSelected(row);setDetail(null);setDetailError(null);
   if(!row.policyId){
     setDetailError('정책이 없는 행은 기준 상세를 조회할 수 없습니다.');
     return;
   }
   setDetailLoading(true);
   try{
     validateDailyBandV4(band);
     const result=await service.detail(part,row.date,row.policyId,band);
     if(current===detailSerial.current)setDetail(result);
   }catch(e){if(current===detailSerial.current)setDetailError(e instanceof Error?e.message:'기준 상세 조회 실패');}
   finally{if(current===detailSerial.current)setDetailLoading(false);}
 };
 const openInspection=(id:string)=>router.push({pathname:'/inspection-live',params:{inspectionId:id}});
 return <SafeAreaView style={s.root}>
   <Stack.Screen options={{headerShown:false}}/>
   <View style={s.header}>
     <Pressable accessibilityRole="button" onPress={()=>router.back()}>
       <Text style={s.link}>‹ 관리자 설정으로 돌아가기</Text>
     </Pressable>
     <Text style={s.title}>날짜별 자동 판정 이력</Text>
     <Text style={s.muted}>실제 서버 · ADMIN 전용 · KST 날짜 기준</Text>
   </View>
   <ScrollView style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
     {access==='checking'&&<ActivityIndicator/>}
     {access==='denied'&&<View style={s.card}>
       <Text style={s.error}>실제 로그인 ADMIN 계정만 조회할 수 있습니다.</Text>
     </View>}
     {access==='admin'&&<>
       <View style={s.card}>
         <Text style={s.strong}>부품 선택</Text>
         <View style={s.chips}>{parts.map(p=><Pressable key={p} accessibilityRole="button"
           accessibilityState={{selected:part===p}}
           onPress={()=>{setPart(p);setRows(null);setSelected(null);setDetail(null);}} style={[s.chip,part===p&&s.chipActive]}>
           <Text style={[s.chipText,part===p&&s.chipTextActive]}>{p}</Text>
         </Pressable>)}</View>
         <Text style={s.strong}>접수 날짜 범위 (서울 기준 · 시작 포함 / 종료 제외)</Text>
         <Text style={s.muted}>YYYY-MM-DD · 최대 92일. 오늘까지 포함하려면 종료일을 내일로 설정하세요.</Text>
         <View style={s.chips}>
           <View style={s.dateCell}><Text style={s.muted}>시작일 (from)</Text>
             <TextInput value={from} onChangeText={x=>{setFrom(x);setRows(null);setSelected(null);setDetail(null);}} style={s.input} autoCorrect={false}
               placeholder="YYYY-MM-DD" maxLength={10}/></View>
           <View style={s.dateCell}><Text style={s.muted}>종료일 (to, 미포함)</Text>
             <TextInput value={to} onChangeText={x=>{setTo(x);setRows(null);setSelected(null);setDetail(null);}} style={s.input} autoCorrect={false}
               placeholder="YYYY-MM-DD" maxLength={10}/></View>
         </View>
         <Pressable style={s.primary} accessibilityRole="button" disabled={loading}
           onPress={()=>{void load();}}>
           <Text style={s.primaryText}>{loading?'조회 중…':'서버 날짜별 통계 조회'}</Text>
         </Pressable>
         <Text style={s.muted}>통계는 서버가 검사 접수 날짜와 당시 정책·모델·보정기로 집계합니다. 모바일에서 수치를 재집계하지 않습니다.</Text>
       </View>
       {loading&&<ActivityIndicator/>}
       {error&&<View style={s.card}><Text style={s.error}>{error}</Text></View>}
       {rows!==null&&<View style={s.card}>
         <Text style={s.strong}>날짜·정책별 결과 · {rows.length}행</Text>
         {rows.length===0&&<Text style={s.muted}>선택 기간의 집계가 없습니다. 백엔드 #53 시험 서버 반영 여부도 확인하세요.</Text>}
         {rows.map((row,index)=>{
           const rate=dailyAiReviewRateV4(row);
           return <View key={row.date+'|'+(row.policyId??'')+'|'+(row.modelVersion??'')+'|'+(row.calibratorVersion??'')+'|'+index} style={s.history}>
             <Text style={s.strong}>{row.date} · {row.policyVersion??'정책 없음'}</Text>
             <Text style={s.muted}>모델 {row.modelVersion??'미제공'} · 보정기 {row.calibratorVersion??'미제공'}</Text>
             <Line label="집계 (AUTO_PASS / AUTO_FAIL / REVIEW)" value={`${row.total}건 (${row.autoPass} / ${row.autoFail} / ${row.review.total})`}/>
             <Line label="REVIEW 완료" value={`${row.review.done}/${row.review.total}건`}/>
             <Line label="수동 전환 (REVIEW에 포함)" value={`${row.manual.done}/${row.manual.total}건`}/>
             <Line label="AI REVIEW 비율 (수동 제외)" value={rate===null?'산출 불가':fraction(rate)}/>
             <Line label="AI 분석 실패 (집계 제외)" value={`${row.failed}건`}/>
             <Line label="AUTO_FAIL 설정" value={row.autoFailEnabled?'켜짐':'꺼짐'}/>
             <Line label="자동 통과 / 불량 기준" value={`${fraction(row.passThreshold,4)} / ${fraction(row.failThreshold,4)}`}/>
             <Line label="판정 확인 근거" value={oppositeEvidenceTextV4(row)}/>
             <Line label="자동 통과→불량 / 자동 불량→통과" value={`${row.confirmedOpposite.autoPassThenFail} / ${row.confirmedOpposite.autoFailThenPass}건`}/>
             <Line label="처리 대기 확인 요청" value={`${row.openRequests}건`}/>
             {row.policyId?<Pressable style={s.outline} accessibilityRole="button"
               onPress={()=>{void viewDetail(row);}}><Text style={s.link}>통과·불량 기준 주변 REVIEW 상세 ›</Text></Pressable>
               :<Text style={s.muted}>정책 없음: 기준 주변 상세 없음</Text>}
           </View>;
         })}
       </View>}
       {selected&&<View style={s.card}>
         <Text style={s.strong}>기준 상세 · {selected.date} · {selected.policyVersion??'정책 없음'}</Text>
         <Text style={s.muted}>구간 폭(band)은 확률 차입니다. 예: 0.05 = 5%p. 기본 0.05, 허용 0.001~0.5.</Text>
         <TextInput value={band} onChangeText={setBand} style={s.input}
           keyboardType="decimal-pad" placeholder="0.05" />
         <Pressable style={s.outline} accessibilityRole="button" disabled={detailLoading}
           onPress={()=>{void viewDetail(selected);}}>
           <Text style={s.link}>{detailLoading?'조회 중…':'선택한 날짜·정책 구간 다시 조회'}</Text>
         </Pressable>
         {detailLoading&&<ActivityIndicator/>}
         {detailError&&<Text style={s.error}>{detailError}</Text>}
         {detail&&<>
           <Line label="정책/기준" value={`${detail.policyVersion} · ${fraction(detail.passThreshold,4)} / ${fraction(detail.failThreshold,4)}`}/>
           <Line label="판정 참고 자료" value={detail.reference===null?'자료 없음':'자료 확인'}/>
           <Band title="통과 기준 바로 위 GOOD REVIEW" band={detail.passBand} onOpen={openInspection}/>
           <Band title="불량 기준 바로 아래 DEFECT REVIEW" band={detail.failBand} onOpen={openInspection}/>
         </>}
       </View>}
       <Text style={s.muted}>통계의 '판정 완료'는 조회 시점 기준입니다. 정책 변경이 과거 검사를 소급 변경하지 않습니다. 확인 자료 없음은 실물 기준 정답이 없다는 의미이며, 품질 정확도나 미검출률을 단정하지 않습니다.</Text>
     </>}
   </ScrollView>
 </SafeAreaView>;
}
const s=StyleSheet.create({
 root:{flex:1,backgroundColor:'#F5F7FB'},header:{padding:18,gap:8},scroll:{flex:1},
 body:{paddingHorizontal:18,paddingBottom:35,gap:12},title:{fontSize:22,fontWeight:'700',color:ink},
 strong:{fontSize:13,fontWeight:'700',color:ink},muted:{color:muted,fontSize:11,lineHeight:18},
 card:{backgroundColor:'#FFF',borderRadius:14,borderColor:'#E4E7EC',borderWidth:1,padding:14,gap:12},
 chips:{flexDirection:'row',flexWrap:'wrap',gap:6},chip:{borderWidth:1,borderRadius:9,borderColor:'#CBD5E1',padding:9},
 chipActive:{backgroundColor:blue,borderColor:blue},chipText:{fontSize:11,fontWeight:'700',color:'#334155'},
 chipTextActive:{color:'#FFF'},dateCell:{flex:1,minWidth:124,gap:6},
 input:{borderWidth:1,borderColor:'#CBD5E1',borderRadius:9,padding:11,fontSize:13,color:ink},
 primary:{backgroundColor:blue,padding:13,borderRadius:10,alignItems:'center'},
 primaryText:{color:'#FFF',fontWeight:'700',fontSize:13},
 outline:{borderWidth:1,borderColor:blue,borderRadius:10,padding:10,alignItems:'center'},
 link:{color:blue,fontSize:12,fontWeight:'700'},error:{color:red,fontSize:12,lineHeight:20},
 line:{flexDirection:'row',alignItems:'flex-start',justifyContent:'space-between',gap:10},
 lineLabel:{flex:0.56,color:muted,fontSize:11,lineHeight:17},
 lineValue:{flex:0.44,color:ink,fontSize:11,fontWeight:'600',textAlign:'right',lineHeight:17},
 history:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingVertical:12,gap:8},
 band:{backgroundColor:'#F8FAFC',padding:12,borderRadius:10,gap:9},
 item:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingTop:9,gap:4},
});
