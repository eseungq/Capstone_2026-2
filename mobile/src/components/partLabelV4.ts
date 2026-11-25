/** 화면 표시만 변환합니다. API의 부품 코드 및 필터 값은 바꾸지 않습니다. */
export function partLabelV4(code: string): string {
  switch(code){
    case 'DOOR': return '도어';
    case 'FRAME': return '프레임';
    case 'COWL_COVER': return '카울커버';
    default: return code;
  }
}
