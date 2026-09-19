from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any

@dataclass(frozen=True,slots=True)
class CodingPlanStep:
    description:str
    tool_name:str
    arguments:dict[str,Any]
    purpose:str

@dataclass(frozen=True,slots=True)
class CodingPlan:
    goal:str
    workspace_id:str
    reasoning_summary:str
    steps:tuple[CodingPlanStep,...]
    expected_files:tuple[str,...]=()
    validation_strategy:tuple[str,...]=()
    completion_conditions:tuple[str,...]=()

    @classmethod
    def parse(cls,value:dict,tool_definitions:list) -> "CodingPlan":
        required={"goal","workspace","reasoning_summary","steps","expected_files","validation_strategy","completion_conditions"}
        if not isinstance(value,dict) or not required.issubset(value): raise ValueError("Coding plan is missing required fields")
        if not all(isinstance(value[key],str) and value[key].strip() for key in ("goal","workspace","reasoning_summary")): raise ValueError("Coding plan text fields must be non-empty")
        definitions={item.name:item for item in tool_definitions}; raw_steps=value["steps"]
        if not isinstance(raw_steps,list) or not 1<=len(raw_steps)<=16: raise ValueError("Coding plan must contain 1 to 16 steps")
        steps=[]
        for raw in raw_steps:
            if not isinstance(raw,dict) or set(raw)!={"description","tool","arguments","purpose"}: raise ValueError("Invalid coding plan step")
            tool=definitions.get(raw["tool"])
            if not tool: raise ValueError(f"Unknown tool in coding plan: {raw['tool']}")
            if not isinstance(raw["arguments"],dict): raise ValueError("Tool arguments must be an object")
            tool.validate_arguments(raw["arguments"])
            steps.append(CodingPlanStep(str(raw["description"]).strip(),tool.name,raw["arguments"],str(raw["purpose"]).strip()))
        lists=[]
        for key in ("expected_files","validation_strategy","completion_conditions"):
            raw=value[key]
            if not isinstance(raw,list) or not all(isinstance(item,str) and item.strip() for item in raw): raise ValueError(f"{key} must be a string list")
            lists.append(tuple(raw))
        if not lists[2]: raise ValueError("At least one completion condition is required")
        return cls(value["goal"].strip(),value["workspace"].strip(),value["reasoning_summary"].strip(),tuple(steps),*lists)

PLAN_FORMAT={"type":"object","required":["goal","workspace","reasoning_summary","steps","expected_files","validation_strategy","completion_conditions"],"properties":{
    "goal":{"type":"string"},"workspace":{"type":"string"},"reasoning_summary":{"type":"string"},
    "steps":{"type":"array","items":{"type":"object","required":["description","tool","arguments","purpose"],"properties":{"description":{"type":"string"},"tool":{"type":"string"},"arguments":{"type":"object"},"purpose":{"type":"string"}}}},
    "expected_files":{"type":"array","items":{"type":"string"}},"validation_strategy":{"type":"array","items":{"type":"string"}},"completion_conditions":{"type":"array","items":{"type":"string"}}}}
