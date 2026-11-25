import React,{useState} from 'react';
import {Pressable,StyleSheet,Text,View} from 'react-native';
import {plusDaysV4} from '../api/backendV4/adminDailyHistoryCoreV4';

function monthStart(value:string){return value.slice(0,7)+'-01';}
function shiftMonth(value:string,delta:number){
  const date=new Date(value+'T00:00:00.000Z');
  date.setUTCMonth(date.getUTCMonth()+delta);
  return date.toISOString().slice(0,10);
}
export function DailyDateCalendarV4({label,value,onSelect,onClose}:{label:string;value:string;onSelect:(date:string)=>void;onClose:()=>void}){
  const [month,setMonth]=useState(()=>monthStart(value));
  const date=new Date(month+'T00:00:00.000Z');
  const offset=date.getUTCDay();
  const next=shiftMonth(month,1);
  const count=Math.round((Date.parse(next+'T00:00:00.000Z')-date.getTime())/86400000);
  const cells=Array.from({length:offset+count},(_,index)=>index<offset?null:plusDaysV4(month,index-offset));
  return <View style={s.panel}>
    <View style={s.row}>
      <Text style={s.title}>{label}</Text>
      <Pressable accessibilityRole="button" onPress={onClose} style={s.nav}><Text style={s.link}>닫기</Text></Pressable>
    </View>
    <View style={s.row}>
      <Pressable accessibilityRole="button" accessibilityLabel="이전 달" onPress={()=>setMonth(v=>shiftMonth(v,-1))} style={s.nav}><Text style={s.link}>‹</Text></Pressable>
      <Text style={s.title}>{date.getUTCFullYear()}년 {date.getUTCMonth()+1}월</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="다음 달" onPress={()=>setMonth(v=>shiftMonth(v,1))} style={s.nav}><Text style={s.link}>›</Text></Pressable>
    </View>
    <View style={s.grid}>
      {['일','월','화','수','목','금','토'].map(day=><View key={day} style={s.cell}><Text style={s.weekday}>{day}</Text></View>)}
      {cells.map((day,index)=>day===null?<View key={'empty-'+index} style={s.cell}/>:
        <Pressable key={day} testID={'daily-date-'+day} style={[s.cell,value===day&&s.selected]}
          accessibilityRole="button" accessibilityLabel={day} accessibilityState={{selected:value===day}} onPress={()=>onSelect(day)}>
          <Text style={[s.day,value===day&&s.selectedText]}>{Number(day.slice(-2))}</Text>
        </Pressable>)}
    </View>
  </View>;
}
const s=StyleSheet.create({
  panel:{gap:8,borderWidth:1,borderColor:'#64748B',borderRadius:10,padding:8,backgroundColor:'#FFFFFF'},
  row:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:4},
  title:{fontSize:14,color:'#111827',fontWeight:'700',flexShrink:1},
  nav:{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',paddingHorizontal:4},
  link:{fontSize:14,color:'#2054D8',fontWeight:'700'},
  grid:{flexDirection:'row',flexWrap:'wrap'},
  cell:{width:'14.285%',minHeight:44,justifyContent:'center',alignItems:'center',borderRadius:8},
  weekday:{color:'#475569',fontSize:13,fontWeight:'600'},day:{color:'#111827',fontSize:14},
  selected:{backgroundColor:'#1E293B'},selectedText:{color:'#FFFFFF',fontWeight:'700'},
});
