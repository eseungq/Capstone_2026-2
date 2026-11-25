import {mergeMonitorAlertsV4, dismissMonitorAlertV4, type MonitorAlertV4} from '../api/backendV4/monitoringPollCore';

type Flow = {token:string; currentId:string};

/** In-memory queue, scoped to one login epoch. No persisted IDs or write requests. */
export function createReviewAlertQueueV4(){
  let epoch=-1;
  let pending:MonitorAlertV4[]=[];
  let flow:Flow|null=null;
  let sequence=0;
  const listeners=new Set<(items:MonitorAlertV4[])=>void>();
  function publish(){for(const listener of listeners)listener([...pending]);}
  function sync(nextEpoch:number){
    if(nextEpoch<epoch)return false;
    if(nextEpoch!==epoch){epoch=nextEpoch;pending=[];flow=null;publish();}
    return true;
  }
  function matches(e:number,token:string,currentId:string){
    return e===epoch&&flow?.token===token&&flow.currentId===currentId;
  }
  return {
    snapshot(e:number){return e===epoch?[...pending]:[];},
    subscribe(listener:(items:MonitorAlertV4[])=>void){listeners.add(listener);return ()=>{listeners.delete(listener);};},
    add(e:number,items:MonitorAlertV4[]){
      if(!sync(e))return;
      pending=mergeMonitorAlertsV4(pending,items.filter(a=>a.inspectionId!==flow?.currentId||a.kind!=='REVIEW_REQUIRED'));publish();
    },
    dismiss(e:number,alert:MonitorAlertV4){
      if(!sync(e))return;pending=dismissMonitorAlertV4(pending,alert);publish();
    },
    begin(e:number,alert:MonitorAlertV4):string|null{
      if(!sync(e)||!pending.some(a=>a.inspectionId===alert.inspectionId&&a.kind===alert.kind))return null;
      pending=dismissMonitorAlertV4(pending,alert);
      flow=alert.kind==='REVIEW_REQUIRED'?{token:String(++sequence),currentId:alert.inspectionId}:null;
      publish();return flow?.token??null;
    },
    matches,
    candidates(e:number,token:string,currentId:string){
      if(!matches(e,token,currentId))return [];
      return pending.filter(a=>a.kind==='REVIEW_REQUIRED'&&a.inspectionId!==currentId);
    },
    discard(e:number,token:string,currentId:string,alert:MonitorAlertV4){
      if(!matches(e,token,currentId))return;
      pending=dismissMonitorAlertV4(pending,alert);publish();
    },
    advance(e:number,token:string,currentId:string,next:MonitorAlertV4){
      if(!matches(e,token,currentId)||next.kind!=='REVIEW_REQUIRED'||!pending.some(a=>a.inspectionId===next.inspectionId&&a.kind===next.kind))return false;
      pending=dismissMonitorAlertV4(pending,next);flow={token,currentId:next.inspectionId};publish();return true;
    },
    stop(e:number,token:string,currentId:string){if(matches(e,token,currentId))flow=null;},
  };
}
export const reviewAlertQueueV4=createReviewAlertQueueV4();

/** Stop immediately on a failed read. Do not consume unresolved alerts. */
export async function findNextReviewAlertV4(queue:ReturnType<typeof createReviewAlertQueueV4>,epoch:number,token:string,currentId:string,
  isCurrent:()=>boolean,readEligible:(alert:MonitorAlertV4)=>Promise<boolean>){
  const valid=()=>isCurrent()&&queue.matches(epoch,token,currentId);
  for(const candidate of queue.candidates(epoch,token,currentId)){
    if(!valid())return null;
    const eligible=await readEligible(candidate);
    if(!valid())return null;
    if(!queue.candidates(epoch,token,currentId).some(a=>a.inspectionId===candidate.inspectionId))continue;
    if(eligible)return candidate;
    queue.discard(epoch,token,currentId,candidate);
  }
  return null;
}
