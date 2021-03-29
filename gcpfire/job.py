from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class JobSpec:
    job_name: str
    job_script_path: str
    image_name: str
    machine_type: str = "n1-standard-4"
    accelerators: Dict[str, Any] = field(default_factory=dict)
    preemptible: bool = True
    additional_meta: List[Dict[str, Any]] = field(default_factory=list)
    startup_script_path: Optional[str] = None
