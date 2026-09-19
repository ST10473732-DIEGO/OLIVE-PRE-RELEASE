from __future__ import annotations
from dataclasses import asdict,dataclass
import time

@dataclass(frozen=True,slots=True)
class ModelTiming:
    model:str;role:str;duration_ms:float;success:bool;time_to_first_token_ms:float|None=None

class ModelMetricsService:
    def __init__(self,max_records=500):self.max_records=max(1,max_records);self.records=[]
    def record(self,model,role,started,success,first_token_at=None):
        item=ModelTiming(model,role,round((time.perf_counter()-started)*1000,2),success,round((first_token_at-started)*1000,2) if first_token_at else None)
        self.records.append(item);self.records=self.records[-self.max_records:];return item
    def summary(self):return [asdict(item) for item in self.records]
