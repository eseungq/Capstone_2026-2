import { actorLabelV4 } from '../api/backendV4/actorLabelV4';
import React,{useCallback,useRef,useState} from 'react';
import {router,Stack,useFocusEffect,useLocalSearchParams} from 'expo-router';
import {ActivityIndicator,Alert,KeyboardAvoidingView,Platform,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {authV4} from '../api/backendV4/authRuntime';
import type {BackendRole} from '../api/backendV4/authCore';
import {createInspectionReadServiceV4} from '../api/backendV4/inspectionReadService';
import {createJudgementRequestServiceV4} from '../api/backendV4/judgementRequestServiceV4';
import {currentJudgementV4,judgementRequestStatusLabelV4} from '../api/backendV4/judgementRequestCoreV4';
import type {InspectionViewV4,FinalJudgementV4} from '../api/backendV4/types';
const reader=createInspectionReadServiceV4({mode:'api',transport:authV4});
const writer=createJudgementRequestServiceV4(authV4);
const err=(e:unknown)=>e instanceof Error?e.message:'서버 요청 오류';

export default function JudgementRequestLiveScreen(){
  const {inspectionId}=useLocalSearchParams<{inspectionId?:string}>();
  const id=typeof inspectionId==='string'?inspectionId:'';
  return <JudgementRequestForm key={id} id={id}/>;
}

function JudgementRequestForm({id}:{id:string}){
  const [role,setRole]=useState<BackendRole|null>(null);
  const [loading,setLoading]=useState(true);
  const [detail,setDetail]=useState<InspectionViewV4|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [area,setArea]=useState('');
  const [reason,setReason]=useState('');
  const [claim,setClaim]=useState<FinalJudgementV4>('FAIL');
  const [submitting,setSubmitting]=useState(false);
  const [submittedRequestId,setSubmittedRequestId]=useState<string|null>(null);
  const scrollRef = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const areaRef = useRef<React.ComponentRef<typeof TextInput>>(null);
  const reasonRef = useRef<React.ComponentRef<typeof TextInput>>(null);
  const revealFocusedInput = () => {
    const field = [areaRef.current, reasonRef.current].find(input => input?.isFocused());
    const content = scrollRef.current?.getInnerViewRef();
    if (!field || !content) return;
    field.measureLayout(content, (_x, y) => {
      if (field.isFocused()) scrollRef.current?.scrollTo({ y: Math.max(0, y - 12), animated: false });
    });
  };
  const submittingRef=useRef(false),serial=useRef(0),mounted=useRef(false);
  const visitEpoch = useRef(authV4.sessionEpoch());
  const isCurrent = useCallback((revision:number) =>
    mounted.current && revision === serial.current && visitEpoch.current === authV4.sessionEpoch(), []);
  const refresh=useCallback(async(expectedRequestId?:string|null)=>{
    const count=++serial.current;
    setLoading(true);setError(null);
    try{
      const session=await authV4.restore();
      if(!isCurrent(count))return;
      if(!session.signedIn)throw new Error('서버 로그인이 필요합니다.');
      const result=await reader.detail(id);
      if(!isCurrent(count))return;
      if(result.source!=='SERVER'||result.value.inspectionId!==id)throw new Error('실제 서버 검사 응답이 아닙니다.');
      if(expectedRequestId && !result.value.judgementRequests.some(request=>request.requestId===expectedRequestId)){
        throw new Error('접수한 요청이 최신 이력에 아직 표시되지 않았습니다.');
      }
      setRole(session.role);setDetail(result.value);
      const current=currentJudgementV4(result.value.finalJudgement,result.value.correction);
      if(current)setClaim(current==='PASS'?'FAIL':'PASS');
    }catch(e){
      if(isCurrent(count)){
        setError(expectedRequestId ? `최신 이력을 다시 조회해 주세요. ${err(e)}` : err(e));
        setDetail(null);
      }
    }
    finally{if(isCurrent(count))setLoading(false);}
  },[id,isCurrent]);
  useFocusEffect(useCallback(() => {
    mounted.current = true;
    const nextEpoch = authV4.sessionEpoch();
    if (visitEpoch.current !== nextEpoch) {
      setArea(''); setReason(''); setSubmittedRequestId(null);
    }
    visitEpoch.current = nextEpoch;
    setDetail(null);
    setRole(null);
    setSubmitting(submittingRef.current);
    void refresh();
    return () => { mounted.current = false; serial.current++; };
  },[refresh]));
  const pendingRequest=detail?.judgementRequests.find(request=>request.status==='OPEN');
  const current = detail ? currentJudgementV4(detail.finalJudgement, detail.correction) : null;
  const available=!loading&&role==='WORKER'&&detail?.judgedBy==='SYSTEM'&&detail.finalJudgement!==null&&!pendingRequest;
  const send=async(confirmedRevision:number)=>{
    if(!isCurrent(confirmedRevision)||submittingRef.current||!detail||!available)return;
    submittingRef.current=true;setSubmitting(true);setError(null);setSubmittedRequestId(null);
    try{
      const session=await authV4.restore();
      if(!isCurrent(confirmedRevision))return;
      if(!session.signedIn||session.role!=='WORKER')throw new Error('작업자 로그인 정보를 확인하세요.');
      // 전송 전 서버 최신 판정·정정·OPEN 요청을 다시 조회하여 화면의 낡은 값으로 POST하지 않습니다.
      const latest=(await reader.detail(id)).value;
      if(!isCurrent(confirmedRevision))return;
      if(latest.inspectionId!==id)throw new Error('선택한 검사를 확인할 수 없습니다. 다시 조회해 주세요.');
      if(latest.judgedBy!=='SYSTEM'||latest.finalJudgement!==detail.finalJudgement||
        currentJudgementV4(latest.finalJudgement,latest.correction)!==
        currentJudgementV4(detail.finalJudgement,detail.correction)||
        latest.judgementRequests.some(x=>x.status==='OPEN')){
        setDetail(latest);
        throw new Error('검사 판정/요청 상태가 변경됐습니다. 최신 상세를 다시 검토해 주세요.');
      }
      const result=await writer.request(session.role,latest,claim,area,reason);
      if(isCurrent(confirmedRevision)){
        setSubmittedRequestId(result.requestId);
        setDetail(null);
        setArea('');setReason('');
        await refresh(result.requestId);
      }
    }catch(e){if(isCurrent(confirmedRevision))setError(err(e));}
    finally{submittingRef.current=false;if(mounted.current)setSubmitting(false);}
  };
  const confirm=()=>{
    if(!available||submitting)return;
    if(claim===current){setError('현재 판정과 다른 판정을 선택해 주세요.');return;}
    if(!reason.trim()){setError('확인 근거를 입력해 주세요.');return;}
    const revision=serial.current;
    Alert.alert('판정 확인 요청 제출',`${detail?.inspectionNo} · 현재 ${currentJudgementV4(detail?.finalJudgement??null,detail?.correction??null)} → 주장 ${claim}\n원본 시스템 판정은 변경되지 않으며 관리자 검토를 요청합니다.`,[
      {text:'취소',style:'cancel'}, {text:'확인 요청',onPress:()=>{void send(revision);}},
    ]);
  };
  return <SafeAreaView style={s.root}>
    <Stack.Screen options={{headerShown:false}}/>
    <KeyboardAvoidingView style={s.flex} behavior={Platform.OS==='ios'?'padding':undefined}>
      <ScrollView ref={scrollRef} style={s.flex} contentContainerStyle={s.body}
        onLayout={revealFocusedInput} keyboardShouldPersistTaps="handled" keyboardDismissMode="none">
        <View style={s.top}>
          <Pressable onPress={()=>router.back()} style={s.backTouch} accessibilityRole="button"><Text style={s.link}>‹ 검사 상세로 돌아가기</Text></Pressable>
          <Text style={s.title}>시스템 판정 확인 요청</Text>
          <Text style={s.muted}>실물·추가 자료와 다른 시스템 판정이 의심될 때만 요청합니다. 최초 판정은 그대로 보존됩니다.</Text>
        </View>
        {loading&&<ActivityIndicator/>}
        {error&&<Text style={s.error}>{error}</Text>}
        {!loading&&!submitting&&<Pressable style={s.outline} onPress={()=>{void refresh(submittedRequestId);}}><Text style={s.link}>최신 검사 다시 조회</Text></Pressable>}
        {submittedRequestId&&<View style={s.card}><Text style={s.success}>
          {pendingRequest?.requestId===submittedRequestId?'판정 확인 요청이 접수되었습니다. 관리자 검토를 기다려 주세요.':'판정 확인 요청이 접수되었습니다.'}
        </Text></View>}
        {detail&&<View style={s.card}>
          <Text style={s.strong}>{detail.inspectionNo} · {detail.partCode}</Text>
          <Text style={s.muted}>최초 판정: {detail.finalJudgement??'미확정'} · {actorLabelV4(detail.judgedBy)}</Text>
          <Text style={s.muted}>현재 판정: {currentJudgementV4(detail.finalJudgement,detail.correction)??'미확정'}</Text>
          {detail.correction&&<Text style={s.muted}>기존 정정: {detail.correction.correctedJudgement} · {detail.correction.correctedBy} ({detail.correction.note})</Text>}
          {detail.judgementRequests.map(r=><View key={r.requestId} style={s.history}>
            <Text style={s.strong}>{judgementRequestStatusLabelV4(r.status)} · 주장 {r.claimedJudgement}</Text>
            <Text style={s.muted}>{r.requestedBy}: {r.reason}</Text>
            {r.resolveNote&&<Text style={s.muted}>관리자 처리: {r.resolveNote}</Text>}
          </View>)}
          {role!=='WORKER'&&<Text style={s.error}>작업자 계정에서만 요청할 수 있습니다.</Text>}
          {role==='WORKER'&&detail.judgedBy!=='SYSTEM'&&<Text style={s.error}>시스템 판정 건이 아니므로 요청 대상이 아닙니다.</Text>}
          {pendingRequest&&pendingRequest.requestId!==submittedRequestId&&<Text style={s.muted}>관리자 검토 대기 중입니다.</Text>}
        </View>}
        {available&&<View style={s.card}>
          <Text style={s.strong}>요청할 판정 (현재 판정과 달라야 함)</Text>
          <View style={s.row}>
            {(['PASS','FAIL'] as const).map(value=><Pressable key={value}
              style={[s.choice,claim===value&&s.choiceOn,value===current&&s.disabled]} disabled={value===current || submitting} onPress={()=>setClaim(value)}
              accessibilityRole="button" accessibilityState={{selected:claim===value,disabled:value===current || submitting}}>
              <Text style={[s.choiceText,claim===value&&s.choiceOnText]}>{value}</Text>
            </Pressable>)}
          </View>
          <Text style={s.strong}>확인 부위 (선택, 최대 100자)</Text>
          <TextInput ref={areaRef} onFocus={revealFocusedInput} value={area} onChangeText={setArea} maxLength={100}
            placeholder="예: 고정핀" placeholderTextColor="#64748B" style={s.input}/>
          <Text style={s.strong}>판정 확인 근거 (필수, 1~500자)</Text>
          <TextInput ref={reasonRef} onFocus={revealFocusedInput} value={reason} onChangeText={setReason} maxLength={500} multiline
            placeholder="실물 관찰 근거를 구체적으로 작성하세요." placeholderTextColor="#64748B" style={[s.input,s.multi]}/>
          <Text style={s.muted}>근거 사진 첨부는 이번 버전의 지원 범위 밖입니다.</Text>
        </View>}
      </ScrollView>
      {available&&<View style={s.footer}>
        <Pressable accessibilityRole="button" accessibilityState={{disabled:submitting}}
          disabled={submitting} style={[s.submit,submitting&&s.disabled]} onPress={confirm}>
          <Text style={s.submitText}>{submitting?'요청 제출 중…':'관리자 판정 확인 요청'}</Text>
        </Pressable>
      </View>}
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
const s=StyleSheet.create({
  backTouch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  root:{flex:1,backgroundColor:'#F5F7FB'},flex:{flex:1},top:{paddingVertical:18,gap:9},
  body:{paddingHorizontal:18,paddingBottom:16,gap:12},
  footer:{paddingHorizontal:18,paddingVertical:8,borderTopWidth:StyleSheet.hairlineWidth,borderColor:'#E4E7EC',backgroundColor:'#FFFFFF'},
  title:{fontSize:22,fontWeight:'700',color:'#111827'},muted:{fontSize: 13,lineHeight:19,color:'#64748B'},
  link:{fontSize: 14,fontWeight:'700',color:'#2054D8'},strong:{fontSize: 14,fontWeight:'700',color:'#111827'},
  card:{backgroundColor:'#FFFFFF',borderColor:'#E4E7EC',borderWidth:1,borderRadius:14,padding:15,gap:12},
  error:{color:'#B42318',fontSize:13,lineHeight:19},success:{color:'#067647',fontSize:13},
  row:{flexDirection:'row',gap:8},choice:{ justifyContent: 'center', minHeight: 44,flex:1,alignItems:'center',padding:13,borderWidth:1,
    borderColor:'#CBD5E1',borderRadius:10},choiceOn:{backgroundColor:'#2054D8',borderColor:'#2054D8'},
  choiceText:{color:'#334155',fontWeight:'700'},choiceOnText:{color:'#FFFFFF'},
  input:{ minHeight: 44,borderWidth:1,borderColor:'#CBD5E1',borderRadius:10,padding:12,color:'#111827',fontSize: 14},
  multi:{minHeight:110,textAlignVertical:'top'},history:{borderTopColor:'#E4E7EC',borderTopWidth:1,paddingTop:10,gap:5},
  outline:{ justifyContent: 'center', minHeight: 44,borderWidth:1,borderColor:'#2054D8',borderRadius:10,padding:11,alignItems:'center'},
  submit:{ justifyContent: 'center', minHeight: 44,backgroundColor:'#2054D8',padding:14,borderRadius:10,alignItems:'center'},
  submitText:{fontSize: 14,color:'#FFFFFF',fontWeight:'700'},disabled:{opacity:.5},
});
