/** 화면 표시만 변환합니다. API의 부품 코드 및 필터 값은 바꾸지 않습니다. */
export function partLabelV4(code: string): string {
  switch(code){
    case 'ALL': return '전체 부품';
    case 'DOOR': return '도어';
    case 'FRAME': return '프레임';
    case 'COWL_COVER': return '카울커버';
    default: return code;
  }
}

export function qualityLabelV4(value:string|null|undefined):string{
  return value==='GOOD'?'정상':value==='DEFECT'?'불량':value??'미제공';
}
export function stratumLabelV4(value:string):string{
  return value==='NEAR'?'기준 근접 구간':value==='MID'?'중간 구간':value==='LOW'?'낮은 구간':value;
}
