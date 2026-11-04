"""Candidate-only inventory binding; common request/CAM/error/lock behavior stays inherited."""
from ai_api.server import Service
from prototype.engine import sha

class CandidateService(Service):
 def __init__(self,engine,version,*args,**kwargs):
  if getattr(engine,'metadata',{}).get('model_version')!=version:raise ValueError('Candidate service version must match loaded engine')
  super().__init__(engine,version,*args,**kwargs)
 def model_inventory(self):
  available=False;metadata=getattr(self.engine,'metadata',{})
  try:
   available=(not self.engine.model.training and self.version==metadata['model_version'] and metadata['model_sha256']==self.engine.expected_checkpoint_sha256==sha(self.engine.checkpoint_path))
  except (OSError,AttributeError,KeyError):pass
  return {'models':[{'partCode':'DOOR','modelVersion':self.version,'available':bool(available),'modelName':metadata.get('model_name'),'modelSha256':metadata.get('model_sha256') if available else None}],'schemaStatus':'development-proposal-field-layout-pending'}
