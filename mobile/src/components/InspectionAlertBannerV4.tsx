import React from 'react';
import {Pressable,StyleSheet,Text,View} from 'react-native';
import {partLabelV4} from './partLabelV4';

/** All inspection notices share size, typography, spacing and action layout. */
export default function InspectionAlertBannerV4({kind,inspectionNo,partCode,count,bottom,onClose,onOpen}:{
 kind:'review'|'failed'|'autoFail';inspectionNo:string|null;partCode:string;count:number;bottom:number;onClose:()=>void;onOpen:()=>void;
}){
 const label=kind==='review'?'판정 대기':kind==='failed'?'AI 분석 실패':'자동 불량';
 const color=kind==='review'?'#2054D8':'#B42318';
 return <View style={[s.banner,{bottom,borderLeftColor:color}]} accessibilityLiveRegion="polite">
   <View style={s.row}>
     <Text style={[s.title,{color}]}>{label}{count>1?` · 외 ${count-1}건`:''}</Text>
     <Pressable accessibilityRole="button" accessibilityLabel={label+' 알림 닫기'} onPress={onClose} style={s.close}><Text style={s.dismiss}>닫기</Text></Pressable>
   </View>
   <Text style={s.description}>{partLabelV4(partCode)} · {inspectionNo??'검사번호 미제공'}</Text>
   <Text style={s.note}>앱 실행 중 확인된 새 검사입니다.</Text>
   <Pressable accessibilityRole="button" onPress={onOpen} style={[s.open,{backgroundColor:color}]}><Text style={s.openText}>검사 상세 보기 ›</Text></Pressable>
 </View>;
}
const s=StyleSheet.create({
 banner:{position:'absolute',left:18,right:18,zIndex:40,elevation:12,backgroundColor:'#FFFFFF',borderWidth:1,borderLeftWidth:5,borderColor:'#CBD5E1',borderRadius:14,padding:14,gap:7,shadowColor:'#000000',shadowOpacity:0.15,shadowRadius:10,shadowOffset:{width:0,height:4}},
 row:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:12},
 title:{flex:1,minWidth:0,fontSize:15,fontWeight:'700'},
 close:{minWidth:44,minHeight:44,alignItems:'center',justifyContent:'center'},
 dismiss:{fontSize:13,fontWeight:'600',color:'#475569'},
 description:{fontSize:13,fontWeight:'600',color:'#111827',flexShrink:1},
 note:{fontSize:13,color:'#475569'},
 open:{minHeight:44,justifyContent:'center',borderRadius:9,padding:10,alignItems:'center'},
 openText:{fontSize:13,color:'#FFFFFF',fontWeight:'700'},
});
