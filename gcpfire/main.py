import logging
import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

loglevel = logging.DEBUG  # logging.INFO
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
logger.debug("Logger initialized.")


def get_credentials():
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/compute"]
    )


def get_logging_client(project, zone):
    logger.debug("Building Logging Client.")
    credentials = get_credentials()
    return build("logging", "v2", credentials=credentials, cache_discovery=False)


def get_compute_client(project, zone):
    logger.debug("Building Compute Client.")
    credentials = get_credentials()
    return build("compute", "v1", credentials=credentials, cache_discovery=False)


def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result["items"] if "items" in result else None


def get_image_link(compute, project, family):
    # Get the latest image
    logger.debug(f"Getting image {family} from project {project}")
    image_response = compute.images().getFromFamily(project=project, family=family).execute()
    logger.debug(f"Got {image_response['selfLink']}")
    return image_response["selfLink"]


def create_instance(
    compute,
    project,
    zone,
    name,
    script_path,
    additional_meta,
    machine_type="n1-standard-4",
    preemptible=True,
    gpus={},
):
    """create instance with <name> and access to a certain gs <bucket>"""
    logger.debug(
        (
            f"Creating Instance {name} with machine_type={machine_type}, preemptible={preemptible}, "
            f"gpus={gpus}, script={script_path}, metadata={additional_meta}"
        )
    )
    source_disk_image = get_image_link(compute, project, "liimba-tesla")

    # Configure the Machine
    machine_type = "zones/%s/machineTypes/%s" % (zone, machine_type)

    # Configure the Accelerators
    guest_accelerators = []
    if len(gpus) > 0:
        for label, count in gpus.items():
            accelerator_type = "projects/%s/zones/%s/acceleratorTypes/%s" % (
                project,
                zone,
                label,
            )
            guest_accelerators.append({"acceleratorCount": count, "acceleratorType": accelerator_type})

    startup_script = open(script_path, "r").read()
    config = {
        "name": name,
        "machineType": machine_type,
        "scheduling": {"preemptible": preemptible, "onHostMaintenance": "TERMINATE", "automaticRestart": False},
        # Specfiy the boot disk and the image to use asa source
        "disks": [
            {
                "boot": True,
                "autoDelete": True,  # TODO: boot disk 50gb kann man reducen?
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
        # Accelerators (GPU/TPU)
        "guestAccelerators": guest_accelerators,
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
                # Automatically install the driver after start-up
                # (not needed for us since we have it already installed in the disk image)
                # {"key": "install-nvidia-driver", "value": True},
                {
                    # Startup script is automatically executed by the
                    # instance upon startup.
                    "key": "startup-script",
                    "value": startup_script,
                },
                {"key": "serial-port-enable", "value": True},
                # {"key": "url", "value": some_variable},
                *additional_meta,
            ]
        },
    }
    return compute.instances().insert(project=project, zone=zone, body=config).execute()


def delete_instance(compute, project, zone, name):
    logger.info(f"Deleting Instance {name}")
    return compute.instances().delete(project=project, zone=zone, instance=name).execute()


def wait_for_operation(compute, project, zone, operation):
    logger.info("Waiting for operation to finish...")
    while True:
        result = compute.zoneOperations().get(project=project, zone=zone, operation=operation).execute()

        if result["status"] == "DONE":
            logger.info("done.")
            if "error" in result:
                raise Exception(result["error"])
            return result

        time.sleep(1)


def wait_for_status(compute, project, zone, instance_id):
    """https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry"""
    """https://cloud.google.com/logging/docs/view/advanced-queries"""
    logs = get_logging_client(project, zone)
    logger.debug("Waiting for startup script exit status...")
    body = {
        "projectIds": [project],
        "resourceNames": [],
        "filter": f'resource.type="gce_instance" AND resource.labels.instance_id="{instance_id}"',
        "serviceAccounts": [
            {
                "email": "default",
                "scopes": [
                    "https://www.googleapis.com/auth/logging.logEntries.list",
                    "https://www.googleapis.com/auth/logging.privateLogEntries.list",
                    "https://www.googleapis.com/auth/logging.views.access",
                ],
            }
        ],
    }
    # entries = logs.entries().list(body=body).execute()
    print(0)
    print(1)


def fire(project, zone, instance_name, script_path, additional_meta, wait=True):
    logger.info("Creating Client.")
    compute = get_compute_client(project, zone)

    logger.info(f"Creating Instance {instance_name}.")
    operation = create_instance(
        compute, project, zone, instance_name, script_path, additional_meta, gpus={"nvidia-tesla-t4": 1}
    )
    wait_for_operation(compute, project, zone, operation["name"])

    instances = list_instances(compute, project, zone)
    if instances is not None:
        logger.info("Instances in project %s and zone %s:" % (project, zone))
        for instance in instances:
            logger.info(" - " + instance["name"])

    our_instance = list(filter(lambda x: x["name"] == instance_name, instances))

    if len(our_instance) == 1:
        logger.info("Instance created.")  # TODO: check our instance is actually here
        instance_id = our_instance[0]["id"]
    elif len(our_instance) > 1:  # TODO: this can DEFINITELY break when we parallelize
        raise "ERROR WE HAVE TWO INSTANCES???"
    else:
        logger.error("Instace was not created.")

    wait_for_status(compute, project, zone, instance_id)

    if wait:
        input("DELETE instance?")
    operation = delete_instance(compute, project, zone, instance_name)
    wait_for_operation(compute, project, zone, operation["name"])


def main():
    PROJECT_ID = "main-composite-287415"
    ZONE = "us-east1-c"
    logger.debug(f"Starting gcpfire with Project ID: {PROJECT_ID}, Zone: {ZONE}")

    input_uri = "gs://dev-video-input/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"
    output_uri = "gs://dev-video-exported/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"

    instance_name = f"analysis{str(time.time()).split('.')[0]}"
    analysis_script_path = os.path.join(
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

    fire(PROJECT_ID, ZONE, instance_name, analysis_script_path, additional_meta)


if __name__ == "__main__":
    main()
