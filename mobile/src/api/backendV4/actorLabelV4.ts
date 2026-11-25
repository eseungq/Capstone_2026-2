export function actorLabelV4(actor: string | null | undefined): string {
  switch (actor) {
    case 'SYSTEM': return '시스템 자동 판정';
    case 'WORKER': return '작업자 판정';
    case 'ADMIN': return '관리자 판정';
    case null:
    case undefined: return '미제공';
    default: return '확인 필요';
  }
}
