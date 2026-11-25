import React from 'react';
import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import Pressable from './TouchPressable';

type Role = 'WORKER' | 'ADMIN';
type Tab = 'monitoring' | 'manage' | 'history' | 'settings';
const tabs: {key: Tab; icon: string; label: string}[] = [
  {key:'monitoring',icon:'▣',label:'모니터링'},
  {key:'manage',icon:'☷',label:'관리'},
  {key:'history',icon:'▤',label:'이력'},
  {key:'settings',icon:'⚙',label:'설정'},
];
export default function LiveBottomNavV4({role,active}:{role:Role;active:Tab}) {
  const open = (key:Tab) => {
    if(key===active) return;
    if(key==='manage'){
      if(role==='ADMIN') router.replace('/manage-live');
      return;
    }
    const pathname = key==='monitoring' ? '/monitoring' : key==='history' ? '/history' : '/settings';
    router.replace({pathname,params:{role,mode:'live'}});
  };
  return <View style={s.nav} accessibilityRole="tablist">
    {tabs.filter(tab=>tab.key!=='manage'||role==='ADMIN').map(tab=>(
      <Pressable key={tab.key} testID={'live-tab-'+tab.key}
        accessibilityRole="tab" accessibilityLabel={tab.label} accessibilityState={{selected:active===tab.key}}
        onPress={()=>open(tab.key)} style={[s.tab,active===tab.key&&s.selected]}>
        <Text style={[s.icon,active===tab.key&&s.selectedText]} importantForAccessibility="no">{tab.icon}</Text>
        <Text style={[s.label,active===tab.key&&s.selectedText]}>{tab.label}</Text>
      </Pressable>
    ))}
  </View>;
}
const s=StyleSheet.create({
  nav:{flexDirection:'row',alignItems:'stretch',gap:3,marginHorizontal:20,marginBottom:6,minHeight:58,padding:4,borderWidth:1,borderColor:'#E4E7EC',borderRadius:15,backgroundColor:'#FFFFFF'},
  tab:{flex:1,minWidth:0,minHeight:48,alignItems:'center',justifyContent:'center',paddingHorizontal:2,paddingVertical:4,borderRadius:10,gap:2},
  selected:{backgroundColor:'#1E293B'},
  icon:{fontSize:18,color:'#475569'},
  label:{fontSize:13,color:'#475569',textAlign:'center',fontWeight:'600'},
  selectedText:{color:'#FFFFFF'},
});
