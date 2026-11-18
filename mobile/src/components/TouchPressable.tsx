import React from 'react';
import { Pressable as NativePressable, StyleSheet } from 'react-native';
import type { PressableProps } from 'react-native';

/** 모든 주요 화면에서 동일한 짧은 터치 피드백을 제공합니다. */
export default function TouchPressable({ style, disabled, children, ...rest }: PressableProps) {
  return (
    <NativePressable
      {...rest}
      disabled={disabled}
      style={(state) => [
        typeof style === 'function' ? style(state) : style,
        state.pressed && !disabled && styles.pressed,
      ]}
    >
      {children}
    </NativePressable>
  );
}
const styles = StyleSheet.create({ pressed: { opacity: 0.76 } });
