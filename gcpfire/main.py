import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from gcpfire import ssh_client as ssh
from gcpfire.keys import delete_local_key, generate_keypair, write_privatekey
from gcpfire.logger import logger

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


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
    if preemptible:
        logger.debug("This instance is pre-emptible and will live for no longer than 24 hours.")

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


def wait_for_response(compute, project, zone, operation):
    logger.info("Waiting for operation to finish...")
    while True:
        result = compute.zoneOperations().get(project=project, zone=zone, operation=operation).execute()

        if result["status"] == "DONE":
            logger.info("done.")
            if "error" in result:
                raise Exception(result["error"])
            return result

        time.sleep(1)


class InstanceNotExistsError(Exception):
    """Requested instance does not exist according to GCP API."""

    pass


def add_ssh_keys(compute, project, zone, instance_name):
    logger.debug(f"Getting instance {instance_name} data.")
    request_instance_get = compute.instances().get(project=project, zone=zone, instance=instance_name).execute()

    if request_instance_get is not None:
        logger.debug("Instance metadata:\n" + str(request_instance_get["metadata"]))

        keys = []
        other_items = []
        fingerprint = request_instance_get["metadata"]["fingerprint"]
        for meta_item in request_instance_get["metadata"]["items"]:
            if meta_item["key"] == "ssh-keys":
                keys.extend(meta_item["value"].split("\n"))
            else:
                other_items.append(meta_item)

        logger.info("Generating keypair.")
        priv, pub = generate_keypair()
        private_key_file = write_privatekey(priv, instance_name, outpath=os.path.join(os.getcwd(), "secrets"))
        logger.info(f"Private key file available at: {private_key_file}")

        keys.append("gcpfire:" + pub)

        body = {"items": [{"key": "ssh-keys", "value": "\n".join(keys)}, *other_items], "fingerprint": fingerprint}

        logger.info("Adding public key to Instance (user:gcpfire)...")
        request_instance_setMetadata = (
            compute.instances().setMetadata(project=project, zone=zone, instance=instance_name, body=body).execute()
        )
        wait_for_response(compute, project, zone, request_instance_setMetadata["name"])

        external_ip = request_instance_get["networkInterfaces"][0]["accessConfigs"][0]["natIP"]

        return (private_key_file, external_ip)
    else:
        logger.error(f"Instance {instance_name} does not exist.")
        raise InstanceNotExistsError


def fire(project, zone, instance_name, script_path, additional_meta, wait=True):
    logger.info("Creating Client.")
    compute = get_compute_client(project, zone)

    logger.info(f"Creating Instance {instance_name}.")
    request = create_instance(
        compute,
        project,
        zone,
        instance_name,
        script_path,
        additional_meta,
        gpus={},
        # gpus={"nvidia-tesla-t4": 1},
        preemptible=False,
    )
    wait_for_response(compute, project, zone, request["name"])

    instances = list_instances(compute, project, zone)
    if instances is not None:
        logger.info("Instances in project %s and zone %s:" % (project, zone))
        for instance in instances:
            logger.info(" - " + instance["name"])

    # Actually we do not need to check for the instance because the API should gaurantee it's up when the request is Done.
    # our_instance = list(filter(lambda x: x["name"] == instance_name, instances))
    # if len(our_instance) == 1:
    #     logger.info("Instance created.")
    #     instance_id = our_instance[0]["id"]
    # elif len(our_instance) > 1:
    #     raise "ERROR WE HAVE TWO INSTANCES???"
    # else:
    #     logger.error("Instace was not created.")

    private_key_file, instance_ip = add_ssh_keys(compute, project, zone, instance_name)

    try:
        execute_job(instance_ip, private_key_file)
    finally:
        cleanup(compute, project, zone, instance_name, private_key_file, wait)


def cleanup(compute, project, zone, instance_name, private_key_file, wait):
    if wait:
        input("DELETE instance? [Enter]")
    request = delete_instance(compute, project, zone, instance_name)
    wait_for_response(compute, project, zone, request["name"])

    delete_local_key(private_key_file)


def execute_job(instance_ip, key):
    # Because we reuse an IP for different instances we have to remove it from ~/.ssh/known_hosts.
    # However, we have to manually remove it because openssh does not allow us to disable KnownHostsFile anymore.
    ssh.remove_host(instance_ip)

    # For some reason the connection does not work on the first try. Maybe because google only adds the key to
    # authorized_keys during the first connection attempt. So we just keep probing the connection a couple times.
    tries = 0
    while tries < 5:
        try:
            ssh.test_connection(instance_ip, key)
        except ssh.RemoteExecutionError:
            # skip to next try if the probing didn't work
            tries += 1
            time.sleep(5)
            continue

        # Otherwise we can continue (but we can still get a ssh.RemoteExecutionError with the next commands)
        # Simple job: upload a bash file and execute it.
        ssh.copy_file(instance_ip, os.path.join(os.getcwd(), "jobs", "analysis.sh"), key)
        run_result = ssh.run_command(instance_ip, "bash analysis.sh", key)

        return run_result

    # we achieved our max # of tries
    raise ssh.RemoteExecutionError


def main():
    PROJECT_ID = "main-composite-287415"
    ZONE = "us-east1-c"
    logger.debug(f"Starting gcpfire with Project ID: {PROJECT_ID}, Zone: {ZONE}")

    input_uri = "gs://dev-video-input/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"
    output_uri = "gs://dev-video-exported/test/10_Hegenberger_vs_Ehret/10_Hegenberger_vs_Ehret.mp4"

    instance_name = f"analysis{str(time.time()).split('.')[0]}"  # TODO: this can DEFINITELY break when we parallelize
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

    fire(PROJECT_ID, ZONE, instance_name, analysis_script_path, additional_meta, wait=False)


if __name__ == "__main__":
    main()
