import logging
import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

PROJECT_ID = "main-composite-287415"
ZONE = "us-east1-c"
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

loglevel = logging.DEBUG  # logging.INFO
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
logger.debug("Logger initialized.")
logger.debug(f"Starting gcpfire with Project ID: {PROJECT_ID}, Zone: {ZONE}")


def get_client(project, zone):
    logger.debug("Building client.")

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/compute"]
    )

    return build("compute", "v1", credentials=credentials, cache_discovery=False)


def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result["items"] if "items" in result else None


def create_instance(compute, project, zone, name, additional_meta):
    """create instance with <name> and access to a certain gs <bucket>"""
    # Get the latest image
    image_response = (
        compute.images()
        .getFromFamily(
            project="deeplearning-platform-release", family="tf2-ent-latest-gpu"
        )
        .execute()
    )
    source_disk_image = image_response["selfLink"]

    # Configure the Machine
    machine_type = "zones/%s/machineTypes/n1-standard-4" % zone
    accelerator_type = "projects/%s/zones/%s/acceleratorTypes/nvidia-tesla-t4" % (
        project,
        zone,
    )
    startup_script = open(
        os.path.join(os.path.dirname(__file__), "startup_script.sh"), "r"
    ).read()
    config = {
        "name": name,
        "machineType": machine_type,
        "preemptible": True,
        "scheduling": {"onHostMaintenance": "TERMINATE", "automaticRestart": False},
        # Specfiy the boot disk and the image to use asa source
        "disks": [
            {
                "boot": True,
                "autoDelete": True,  # TODO: boot disk size?
                "initializeParams": {"sourceImage": source_disk_image},
            }
        ],
        # Specify Network Interface with NAT to accesss the public internet
        "networkInterfaces": [
            {
                "network": "global/networks/default",
                "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
            }
        ],
        "guestAccelerators": [
            {"acceleratorCount": 1, "acceleratorType": accelerator_type}
        ],
        # Allow Instance to access cloud storage and logging
        "serviceAccounts": [
            {
                "email": "default",
                "scopes": [
                    "https://www.googleapis.com/auth/devstorage.read_write",
                    "https://www.googleapis.com/auth/logging.write",
                ],
            }
        ],
        # Metadata is readable from the instance and allows you to pass
        # configuration from deployment scripts to instance
        "metadata": {
            "items": [
                {"key": "install-nvidia-driver", "value": True},
                {
                    # Startup script is automatically executed by the
                    # instance upon startup.
                    "key": "startup-script",
                    "value": startup_script,
                },
                # {"key": "url", "value": image_url},
                *additional_meta,
            ]
        },
    }
    return compute.instances().insert(project=project, zone=zone, body=config).execute()


def delete_instance(compute, project, zone, name):
    return (
        compute.instances().delete(project=project, zone=zone, instance=name).execute()
    )


def wait_for_operation(compute, project, zone, operation):
    logger.info("Waiting for operation to finish...")
    while True:
        result = (
            compute.zoneOperations()
            .get(project=project, zone=zone, operation=operation)
            .execute()
        )

        if result["status"] == "DONE":
            logger.info("done.")
            if "error" in result:
                raise Exception(result["error"])
            return result

        time.sleep(1)


def main(project, bucket, zone, instance_name, wait=True):

    video_name = "123test"
    additional_meta = [
        {"key": "docker_image", "value": f"gcr.io/{PROJECT_ID}/aio:latest"},
        {"key": "bucket", "value": bucket},
        {"key": "video_name", "value": video_name},
    ]

    logger.info("Creating Client.")
    compute = get_client(PROJECT_ID, ZONE)
    logger.info("Creating Instance.")
    operation = create_instance(compute, project, zone, instance_name, additional_meta)
    wait_for_operation(compute, project, zone, operation["name"])
    instances = list_instances(compute, PROJECT_ID, ZONE)
    logger.info("Instances in project %s and zone %s:" % (project, zone))
    for instance in instances:
        logger.info(" - " + instance["name"])
    logger.info("Instance created.")
    if wait:
        input("Delete instance?")
    logger.info("Deleting Instance.")
    operation = delete_instance(compute, project, zone, instance_name)
    wait_for_operation(compute, project, zone, operation["name"])


if __name__ == "__main__":
    main(PROJECT_ID, "test_bucket", ZONE, f"test1{str(time.time()).split('.')[0]}")
