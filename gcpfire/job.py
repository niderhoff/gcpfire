class JobSpec:
    def __init__(
        self,
        job_name,
        job_script_path,
        image_name,
        machine_type="n1-standard-4",
        accelerators={},
        preemptible=True,
        additional_meta=None,
        startup_script_path=None,
        wait=False,
    ):
        self.job_name = job_name
        self.job_script_path = job_script_path
        self.image_name = image_name
        self.machine_type = machine_type
        self.accelerators = accelerators
        self.preemptible = preemptible
        self.additional_meta = additional_meta
        self.startup_script_path = startup_script_path
        self.wait = wait
