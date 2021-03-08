import os
import time
from logging import DEBUG as loglevel

from gcpfire.compute import ComputeAPI
from gcpfire.job import JobSpec
from gcpfire.logger import logger

PROJECT_ID = "main-composite-287415"
ZONE = "us-east1-c"

logger.setLevel(loglevel)
logger.debug(f"Starting gcpfire with Project ID: {PROJECT_ID}, Zone: {ZONE}")

# Set this to False for debugging purposes, because this way we have a higher chance of getting the config we want
PREEMPTIBLE = False

# Test Data
input_uri = "gs://dev-video-input/videos/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"
rallies_uri = "gs://dev-video-input/analyzed/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.csv"
output_uri = "gs://dev-video-exported/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"


def analysis_task():
    """Analysis: Extract Frames & classify rallies"""
    analysis_job_name = (
        f"analysis-{str(time.time()).split('.')[0]}"  # TODO: this can DEFINITELY break when we parallelize
    )
    analysis_script_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)),
        "jobs",
        "analysis.sh",
    )
    analysis_meta = [
        {"key": "project_id", "value": PROJECT_ID},
        {
            "key": "input_uri",
            "value": input_uri,
        },
        {
            "key": "rallies_uri",
            "value": rallies_uri,
        },
    ]

    # Define type & number of GPUs for EACH machine
    gpus = {"nvidia-tesla-t4": 1}
    machine_type = "n1-standard-4"
    image_name = "liimba-tesla"  # TODO: enable global images (currently limited to images from OUR project)

    compute_api = ComputeAPI(PROJECT_ID, ZONE)
    job = JobSpec(analysis_job_name, analysis_script_path, image_name, machine_type, gpus, PREEMPTIBLE, analysis_meta)

    compute_api.fire(job, wait=True)


def exporter_task():
    """Exporter: Use rallies csv to cut & export video"""
    exporter_job_name = f"exporter-{str(time.time()).split('.')[0]}"
    exporter_script_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)),
        "jobs",
        "exporter.sh",
    )
    exporter_meta = [
        {"key": "project_id", "value": PROJECT_ID},
        {
            "key": "input_uri",
            "value": input_uri,
        },
        {
            "key": "rallies_uri",
            "value": rallies_uri,
        },
        {
            "key": "output_uri",
            "value": output_uri,
        },
    ]
    gpus = {"nvidia-tesla-t4": 1}
    machine_type = "n1-standard-4"
    image_name = "liimba-tesla"  # TODO: enable global images (currently limited to images from OUR project)

    compute_api = ComputeAPI(PROJECT_ID, ZONE)
    job = JobSpec(exporter_job_name, exporter_script_path, image_name, machine_type, gpus, PREEMPTIBLE, exporter_meta)

    compute_api.fire(job, wait=True)


if __name__ == "__main__":
    analysis_task()
    exporter_task()
