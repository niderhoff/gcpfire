import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from gcpfire.instance import Instance, InstanceSpecBuilder
from gcpfire.keys import generate_keypair, write_privatekey
from gcpfire.logger import logger

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
HARD_LIMIT_MAX_INSTANCES = 10


class InstanceNotExistsError(Exception):
    """Requested instance does not exist according to GCP API."""

    pass


class TooManyInstancesError(Exception):
    """More instances are running than we have allowed for this Project"""

    pass


class NoInstancesError(Exception):
    """We have created an instances but GCP reports no instances. This is a FATAL errror and should not happen."""

    pass


def get_credentials():
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/compute"]
    )


def get_compute_client():
    logger.debug("Building Compute Client.")
    credentials = get_credentials()
    return build("compute", "v1", credentials=credentials, cache_discovery=False)


def get_logging_client():
    logger.debug("Building Logging Client.")
    credentials = get_credentials()
    return build("logging", "v2", credentials=credentials, cache_discovery=False)


class ComputeAPI:
    def __init__(self, project, zone):
        logger.info("Creating Compute API Instance.")
        self.project = project
        self.zone = zone
        self.compute = get_compute_client()

    def get_image_link(self, project, family):
        # Get the latest image
        logger.debug(f"Getting image {family} from project {project}")
        image_response = self.compute.images().getFromFamily(project=project, family=family).execute()
        logger.debug(f"Got {image_response['selfLink']}")
        return image_response["selfLink"]

    def create_instance(self, instance_builder):
        logger.info(f"Creating Instance {instance_builder.name}.")
        instance_spec = instance_builder.build(self.project, self.zone)
        request = (
            self.compute.instances().insert(project=self.project, zone=self.zone, body=instance_spec.config).execute()
        )
        result = self.wait_for_response(request["name"])
        return result

    def wait_for_response(self, operation):
        logger.info("Waiting for operation to finish...")
        while True:
            result = (
                self.compute.zoneOperations().get(project=self.project, zone=self.zone, operation=operation).execute()
            )

            if result["status"] == "DONE":
                logger.info("done.")
                if "error" in result:
                    raise Exception(result["error"])
                return result

            time.sleep(1)

    def list_instances(self):
        result = self.compute.instances().list(project=self.project, zone=self.zone).execute()
        return result["items"] if "items" in result else None

    def add_ssh_keys(self, instance):
        logger.debug(f"Getting instance {instance.name} data.")
        request_instance_get = (
            self.compute.instances().get(project=self.project, zone=self.zone, instance=instance.name).execute()
        )

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
            private_key_file = write_privatekey(priv, instance.name, outpath=os.path.join(os.getcwd(), "secrets"))
            logger.info(f"Private key file available at: {private_key_file}")

            keys.append("gcpfire:" + pub)

            body = {"items": [{"key": "ssh-keys", "value": "\n".join(keys)}, *other_items], "fingerprint": fingerprint}

            logger.info("Adding public key to Instance (user:gcpfire)...")
            request_instance_setMetadata = (
                self.compute.instances()
                .setMetadata(project=self.project, zone=self.zone, instance=instance.name, body=body)
                .execute()
            )
            self.wait_for_response(request_instance_setMetadata["name"])

            external_ip = request_instance_get["networkInterfaces"][0]["accessConfigs"][0]["natIP"]

            instance.external_ip = external_ip
            instance.private_key_file = private_key_file
        else:
            logger.error(f"Instance {instance.name} does not exist.")
            raise InstanceNotExistsError

    def delete_instance(self, instance):
        logger.info(f"Deleting Instance {instance.name}")
        return self.compute.instances().delete(project=self.project, zone=self.zone, instance=instance.name).execute()

    def cleanup(self, instance, wait):
        if wait:
            input(f"DELETE instance {instance.name}? [Enter]")
        request = self.delete_instance(instance)
        self.wait_for_response(request["name"])

        instance.delete_local_keyfile()

    def fire(self, job):
        image_link = self.get_image_link(self.project, job.image_name)

        instance_spec = InstanceSpecBuilder(
            job.job_name,
            image_link,
            job.additional_meta,
            job.machine_type,
            job.accelerators,
            job.preemptible,
            job.startup_script_path,
        )

        instances = self.list_instances()
        if instances is not None and len(instances) > HARD_LIMIT_MAX_INSTANCES:
            raise TooManyInstancesError

        self.create_instance(instance_spec)

        instances = self.list_instances()
        if instances is not None:
            logger.info("Instances in project %s and zone %s:" % (self.project, self.zone))
            for instance in instances:
                logger.info(" - " + instance["name"])
        else:
            raise NoInstancesError

        # TODO: save state & populate instances
        # this_job_instances = filter(lambda x: x["name"] == job.job_name, instances).map(lambda x: Instance(x["name"], self.project, self.zone))

        this_instance = Instance(instance_spec.name, self.project, self.zone)
        self.add_ssh_keys(this_instance)  # add ssh keys to instance

        try:
            this_instance.remote_execute_script(job.job_script_path)
        finally:
            self.cleanup(this_instance, job.wait)
