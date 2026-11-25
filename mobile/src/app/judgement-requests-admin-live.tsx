import { actorLabelV4 } from '../api/backendV4/actorLabelV4';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {router,Stack,useFocusEffect} from 'expo-router';
import {ActivityIndicator,Alert,KeyboardAvoidingView,Platform,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {authV4} from '../api/backendV4/authRuntime';
import {createJudgementRequestServiceV4} from '../api/backendV4/judgementRequestServiceV4';
import {judgementRequestStatusLabelV4} from '../api/backendV4/judgementRequestCoreV4';
import type {
  JudgementRequestV4,JudgementQueueStatusV4,JudgementResolveDecisionV4,
  JudgementQueuePageV4,
} from '../api/backendV4/judgementRequestCoreV4';

const writer=createJudgementRequestServiceV4(authV4);
const err=(e:unknown)=>e instanceof Error?e.message:'서버 조회/처리 오류';
const parts=['','DOOR','FRAME','COWL_COVER'];

export default function JudgementRequestsAdminLiveScreen(){
  const [admin,setAdmin]=useState(false);
  const [authLoading,setAuthLoading]=useState(true);
  const [status,setStatus]=useState<JudgementQueueStatusV4>('OPEN');
  const [partCode,setPartCode]=useState('');
  const [page,setPage]=useState<JudgementQueuePageV4|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [selected,setSelected]=useState<JudgementRequestV4|null>(null);
  const [decision,setDecision]=useState<JudgementResolveDecisionV4>('KEEP');
  const [note,setNote]=useState('');
  const [processing,setProcessing]=useState(false);
  const [message,setMessage]=useState<string|null>(null);
  const generation=useRef(0),locked=useRef(false),mounted=useRef(true);
  const confirmation=useRef(0);
  const scrollRef=useRef<React.ComponentRef<typeof ScrollView>>(null);
  const noteRef=useRef<React.ComponentRef<typeof TextInput>>(null);
  const revealNote=()=>{
    const input=noteRef.current;
    const content=scrollRef.current?.getInnerViewRef();
    if(!input?.isFocused()||!content)return;
    input.measureLayout(content,(_x,y)=>{
      if(input.isFocused())scrollRef.current?.scrollTo({y:Math.max(0,y-12),animated:false});
    });
  };
  const sessionEpoch=useRef(authV4.sessionEpoch()).current;

  useFocusEffect(useCallback(()=>()=>{ confirmation.current++; },[]));

  useEffect(()=>{
    mounted.current=true;let cancelled=false;
    void authV4.restore().then(session=>{
      if(!cancelled)setAdmin(session.signedIn&&session.role==='ADMIN');
    }).catch(()=>{if(!cancelled)setAdmin(false);})
      .finally(()=>{if(!cancelled)setAuthLoading(false);});
    return()=>{cancelled=true;mounted.current=false;generation.current++;};
  },[]);

  const load=async(pageNum:number,append:boolean,nextStatus=status,nextPart=partCode)=>{
    const n=++generation.current;
    setLoading(true);setError(null);
    try{
      const session=await authV4.restore();
      if(!session.signedIn||session.role!=='ADMIN')throw new Error('관리자 권한을 다시 확인해 주세요.');
      const result=await writer.list(session.role,{status:nextStatus,partCode:nextPart||undefined,page:pageNum,size:20});
      if(!mounted.current||generation.current!==n)return;
      const prior=append&&page?page.items:[];
      const ids=new Set([...prior,...result.items].map(x=>x.requestId));
      if(ids.size!==prior.length+result.items.length) {
        throw new Error('서로 다른 페이지에 중복 요청 ID가 있습니다.');
      }
      setPage({...result,items:[...prior,...result.items]});
    }catch(e){if(mounted.current&&generation.current===n)setError(err(e));}
    finally{if(mounted.current&&generation.current===n)setLoading(false);}
  };
  useEffect(()=>{
    if(!authLoading&&admin){setPage(null);setSelected(null);void load(0,false);}
    // filters/load are intentionally triggered only by these inputs, not by page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[admin,authLoading,status,partCode]);

  const resolve=async(ticket:number)=>{
    const current=()=>mounted.current&&confirmation.current===ticket&&authV4.sessionEpoch()===sessionEpoch;
    if(!current()||!selected||selected.status!=='OPEN'||locked.current)return;
    locked.current=true;setProcessing(true);setError(null);setMessage(null);
    try{
      const session=await authV4.restore();
      if(!current())return;
      if(!session.signedIn||session.role!=='ADMIN')throw new Error('관리자 계정으로 다시 로그인해 주세요.');
      const reply=await writer.resolve(session.role,selected,decision,note);
      if(!current())return;
      setMessage(`${reply.request.inspectionNo} 요청을 ${judgementRequestStatusLabelV4(reply.request.status)} 처리했습니다.`);
      setSelected(null);setNote('');setPage(null);
      await load(0,false);
    }catch(e){if(current())setError(err(e));}
    finally{
      if(confirmation.current===ticket)confirmation.current++;
      locked.current=false;
      if(mounted.current)setProcessing(false);
    }
  };
  const confirm=()=>{
    if(!selected||processing)return;
    if(!note.trim()){setError('관리자 처리 근거를 입력해 주세요.');return;}
    const ticket=++confirmation.current;
    Alert.alert('관리자 판정 요청 처리',
      `${selected.inspectionNo} · 최초 ${selected.originalJudgement} · 현재 ${selected.currentJudgement} · 작업자 주장 ${selected.claimedJudgement}\n${decision==='KEEP'?'현재 판정을 유지합니다.':'요청한 판정으로 정정 기록을 남깁니다.'} 최초 시스템 판정은 변경되지 않습니다.`,
      [{text:'취소',style:'cancel'},{text:decision==='KEEP'?'유지 처리':'정정 처리',
        style:decision==='CORRECT'?'destructive':'default',onPress:()=>{void resolve(ticket);}}]);
  };
  return <SafeAreaView style={s.root}>
    <Stack.Screen options={{headerShown:false}}/>
    <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <ScrollView ref={scrollRef} style={{flex:1}} contentContainerStyle={s.body}
      onLayout={revealNote} keyboardShouldPersistTaps="handled" keyboardDismissMode="none">
      <View style={s.top}>
        <Pressable onPress={()=>router.back()} style={s.backTouch} accessibilityRole="button"><Text style={s.link}>‹ 관리자 화면으로</Text></Pressable>
        <Text style={s.title}>판정 확인 요청 관리</Text>
        <Text style={s.muted}>요청별 유지·정정 근거를 남깁니다. 최초 판정은 보존됩니다.</Text>
      </View>
      {authLoading?<ActivityIndicator/>:!admin?<Text style={s.error}>관리자 계정으로 로그인해 주세요.</Text>:<>
        <View style={s.card}>
          <Text style={s.strong}>조회 상태</Text>
          <View style={s.row}>
            {(['OPEN','RESOLVED','ALL'] as const).map(x=><Pressable key={x}
              style={[s.filter,status===x&&s.filterOn]} accessibilityRole="button"
              accessibilityState={{selected:status===x}}
              disabled={processing} onPress={()=>{if(x===status)return;confirmation.current++;setStatus(x);setPage(null);setSelected(null);}}>
              <Text style={[s.filterText,status===x&&s.filterTextOn]}>
                {x==='OPEN'?'대기':x==='RESOLVED'?'처리 완료':'전체'}
              </Text>
            </Pressable>)}
          </View>
          <Text style={s.strong}>부품</Text>
          <View style={s.rowWrap}>
            {parts.map(x=><Pressable key={x||'ALL'} style={[s.part,partCode===x&&s.partOn]}
              disabled={processing} onPress={()=>{if(x===partCode)return;confirmation.current++;setPartCode(x);setPage(null);setSelected(null);}}>
              <Text style={[s.filterText,partCode===x&&s.filterTextOn]}>{x||'전체'}</Text>
            </Pressable>)}
          </View>
          <Pressable style={s.outline} disabled={loading||processing} onPress={()=>{confirmation.current++;void load(0,false);}}>
            <Text style={s.link}>요청 목록 새로고침</Text>
          </Pressable>
          {loading&&<ActivityIndicator/>}
          {error&&<Text style={s.error}>{error}</Text>}
          {message&&<Text style={s.success}>{message}</Text>}
          {page&&<>
            <Text style={s.muted}>전체 {page.totalElements}건 · {page.page+1}/{Math.max(1,page.totalPages)}페이지</Text>
            {page.items.length===0&&<Text style={s.muted}>선택 조건의 요청이 없습니다.</Text>}
            {page.items.map(item=><Pressable key={item.requestId} style={s.entry} disabled={processing}
              onPress={()=>{confirmation.current++;setSelected(item);setNote('');setDecision('KEEP');}}>
              <Text style={s.strong}>{item.inspectionNo} · {item.partCode} · {judgementRequestStatusLabelV4(item.status)}</Text>
              <Text style={s.muted}>{item.originalJudgement} · 시스템 자동 판정 → 요청 {item.claimedJudgement}</Text>
              <Text style={s.link}>내용 검토 ›</Text>
            </Pressable>)}
            {page.page+1<page.totalPages&&<Pressable style={s.outline} disabled={loading||processing}
              onPress={()=>{void load(page.page+1,true);}}>
              <Text style={s.link}>다음 페이지 20건 불러오기</Text>
            </Pressable>}
          </>}
        </View>
        {selected&&<View style={s.card}>
          <Text style={s.strong}>{selected.inspectionNo} · 요청 상세</Text>
          <Text style={s.muted}>최초 판정: {selected.originalJudgement} · {actorLabelV4(selected.originalJudgedBy)}</Text>
          <Text style={s.muted}>요청 당시 현재 판정: {selected.currentJudgement}</Text>
          <Text style={s.muted}>작업자 주장: {selected.claimedJudgement}</Text>
          <Text style={s.muted}>요청자: {selected.requestedBy} · {selected.requestedAt}</Text>
          <Text style={s.muted}>부위: {selected.area??'미제공'}</Text>
          <Text style={s.strong}>작업자 확인 근거</Text>
          <Text style={s.muted}>{selected.reason}</Text>
          <Pressable style={s.outline} onPress={()=>router.push({pathname:'/inspection-live',
            params:{inspectionId:selected.inspectionId}})}>
            <Text style={s.link}>원본 사진·AI 근거 포함 검사 상세 보기 ›</Text>
          </Pressable>
          {selected.status==='OPEN'?<>
            <Text style={s.strong}>처리 선택</Text>
            <View style={s.row}>
              {(['KEEP','CORRECT'] as const).map(x=><Pressable key={x}
                style={[s.filter,decision===x&&s.filterOn]} disabled={processing} onPress={()=>{confirmation.current++;setDecision(x);}}
                accessibilityRole="button" accessibilityState={{selected:decision===x}}>
                <Text style={[s.filterText,decision===x&&s.filterTextOn]}>
                  {x==='KEEP'?'현재 판정 유지':'요청 판정으로 정정'}
                </Text>
              </Pressable>)}
            </View>
            <Text style={s.strong}>관리자 처리 근거 (필수, 1~500자)</Text>
            <TextInput ref={noteRef} onFocus={revealNote} style={s.input} value={note} editable={!processing} onChangeText={text=>{confirmation.current++;setNote(text);}} multiline
              maxLength={500} placeholder="검토 근거를 입력해 주세요." placeholderTextColor="#64748B" />
          </>:<>
            <Text style={s.success}>{judgementRequestStatusLabelV4(selected.status)}</Text>
            <Text style={s.muted}>관리자: {selected.resolvedBy??'미제공'}</Text>
            <Text style={s.muted}>처리 근거: {selected.resolveNote??'미제공'}</Text>
          </>}
        </View>}
      </>}
    </ScrollView>
    {admin && !authLoading && selected?.status==='OPEN' && (
      <View style={s.footer}>
        <Pressable accessibilityRole="button" accessibilityState={{disabled:processing}}
          style={[s.submit,processing&&s.disabled]} disabled={processing} onPress={confirm}>
          <Text style={s.submitText}>
            {processing?'처리 중…':decision==='KEEP'?'판정 유지 전 최종 확인':'정정 기록 전 최종 확인'}
          </Text>
        </Pressable>
      </View>
    )}
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
const s=StyleSheet.create({
  backTouch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
 root:{flex:1,backgroundColor:'#F5F7FB'},top:{paddingVertical:18,gap:8},title:{fontSize:22,fontWeight:'700',color:'#111827'},
 body:{paddingHorizontal:18,paddingBottom:16,gap:12},
 footer:{paddingHorizontal:18,paddingVertical:8,borderTopWidth:StyleSheet.hairlineWidth,borderColor:'#E4E7EC',backgroundColor:'#FFFFFF'},
 card:{backgroundColor:'#FFFFFF',borderColor:'#E4E7EC',borderWidth:1,borderRadius:14,padding:14,gap:12},
 link:{fontSize: 14,color:'#2054D8',fontWeight:'700'},strong:{fontSize: 14,color:'#111827',fontWeight:'700'},
 muted:{fontSize: 13,color:'#64748B',lineHeight:18},error:{fontSize: 13,color:'#B42318',lineHeight:18},
 success:{color:'#067647',fontWeight:'700',fontSize: 13},
 row:{flexDirection:'row',gap:8},rowWrap:{flexDirection:'row',flexWrap:'wrap',gap:6},
 filter:{ justifyContent: 'center', minHeight: 44,flex:1,borderRadius:9,borderWidth:1,borderColor:'#CBD5E1',alignItems:'center',paddingVertical:11,paddingHorizontal:5},
 filterOn:{backgroundColor:'#2054D8',borderColor:'#2054D8'},
 filterText:{color:'#334155',fontWeight:'700',fontSize: 12},filterTextOn:{color:'#FFFFFF'},
 part:{ justifyContent: 'center', minHeight: 44,padding:9,borderRadius:8,borderWidth:1,borderColor:'#CBD5E1'},
 partOn:{backgroundColor:'#2054D8',borderColor:'#2054D8'},
 outline:{ justifyContent: 'center', minHeight: 44,borderColor:'#2054D8',borderWidth:1,borderRadius:9,padding:12,alignItems:'center'},
 entry:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingVertical:12,gap:6},
 input:{borderWidth:1,borderColor:'#CBD5E1',borderRadius:10,padding:12,minHeight:90,
   fontSize: 14,color:'#111827',textAlignVertical:'top'},
 submit:{ justifyContent: 'center', minHeight: 44,backgroundColor:'#2054D8',borderRadius:10,padding:14,alignItems:'center'},
 submitText:{color:'#FFFFFF',fontWeight:'700',fontSize: 14},disabled:{opacity:.5},
});
