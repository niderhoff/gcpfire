import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from gcpfire import ssh_client as ssh
from gcpfire.exceptions import InstanceNotExistsError
from gcpfire.instance import InstanceDefinitionBuilder
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


def create_instance(compute, project, zone, instance_def):
    instance_def.build(project, zone)
    request = compute.instances().insert(project=project, zone=zone, body=instance_def.config).execute()
    result = wait_for_response(compute, project, zone, request["name"])
    return result


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


def fire(
    project,
    zone,
    instance_name,
    image_name,
    script_path,
    additional_meta,
    machine_type,
    accelerators,
    preemptible=True,
    wait=True,
):
    logger.info("Creating Client.")
    compute = get_compute_client(project, zone)

    logger.info(f"Creating Instance {instance_name}.")
    image_link = get_image_link(compute, project, image_name)
    instance_def = InstanceDefinitionBuilder(
        instance_name, image_link, additional_meta, machine_type, accelerators, preemptible, script_path
    )
    create_instance(compute, project, zone, instance_def)

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
    gpus = {}
    # gpus = {"nvidia-tesla-t4": 1}
    machine_type = "n1-standard-4"
    preemptible = False
    image_name = "liimba-tesla"

    fire(
        PROJECT_ID,
        ZONE,
        instance_name,
        image_name,
        analysis_script_path,
        additional_meta,
        machine_type,
        gpus,
        preemptible,
        wait=False,
    )


if __name__ == "__main__":
    main()
