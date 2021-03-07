import os
import time

from gcpfire.compute import ComputeAPI
from gcpfire.logger import logger


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


def main():
    PROJECT_ID = "main-composite-287415"
    ZONE = "us-east1-c"
    logger.debug(f"Starting gcpfire with Project ID: {PROJECT_ID}, Zone: {ZONE}")

    input_uri = "gs://dev-video-input/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"
    output_uri = "gs://dev-video-exported/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"

    job_name = f"analysis{str(time.time()).split('.')[0]}"  # TODO: this can DEFINITELY break when we parallelize
    job_script_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)),
        "jobs",
        "analysis.sh",
    )
    additional_meta = [
        {"key": "project_id", "value": PROJECT_ID},
        {
            "key": "input_uri",
            "value": input_uri,
        },
        {
            "key": "output_uri",
            "value": output_uri,
        },
    ]

    # Define type & number of GPUs for EACH machine
    gpus = {}
    # gpus = {"nvidia-tesla-t4": 1}
    machine_type = "n1-standard-4"

    # Set this to False for debugging purposes, because this way we have a higher chance of getting the config we want
    preemptible = False
    image_name = "liimba-tesla"  # TODO: enable global images (currently limited to images from OUR project)

    compute_api = ComputeAPI(PROJECT_ID, ZONE)
    job = JobSpec(job_name, job_script_path, image_name, machine_type, gpus, preemptible, additional_meta)

    compute_api.fire(job)


if __name__ == "__main__":
    main()
