import React, {useCallback,useRef} from 'react';
import {useFocusEffect} from 'expo-router';
import {Keyboard,Platform,ScrollView,TextInput} from 'react-native';

type ScrollRef=React.RefObject<React.ComponentRef<typeof ScrollView>|null>;
type Input=React.ComponentRef<typeof TextInput>;

/** KeyboardAvoidingView owns the insets. Only scroll the focused field into
 * the resized viewport, without adding a second keyboard inset. */
export function useRevealFocusedInputV4(scrollRef:ScrollRef, getFocusedField:()=>Input|null|undefined){
  const active=useRef(false);
  const reveal=useCallback(()=>{
    if(!active.current||Platform.OS!=='ios')return;
    const field=getFocusedField();
    const content=scrollRef.current?.getInnerViewRef();
    if(!field?.isFocused()||!content)return;
    field.measureLayout(content,(_x,y)=>{
      if(active.current&&getFocusedField()===field&&field.isFocused()){
        scrollRef.current?.scrollTo({y:Math.max(0,y-12),animated:false});
      }
    });
  },[getFocusedField,scrollRef]);
  useFocusEffect(useCallback(()=>{
    active.current=true;
    const subscription=Platform.OS==='ios'?Keyboard.addListener('keyboardDidShow',reveal):null;
    return()=>{active.current=false;subscription?.remove();};
  },[reveal]));
  return reveal;
}
