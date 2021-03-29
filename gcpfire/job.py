from typing import Any, Dict, Optional


class JobSpec:
    def __init__(
        self,
        job_name: str,
        job_script_path: str,
        image_name: str,
        machine_type: str = "n1-standard-4",
        accelerators: Dict[str, Any] = {},
        preemptible: bool = True,
        additional_meta: Optional[Dict[str, Any]] = None,
        startup_script_path: Optional[str] = None,
    ):
        self.job_name = job_name
        self.job_script_path = job_script_path
        self.image_name = image_name
        self.machine_type = machine_type
        self.accelerators = accelerators
        self.preemptible = preemptible
        self.additional_meta = additional_meta
        self.startup_script_path = startup_script_path
