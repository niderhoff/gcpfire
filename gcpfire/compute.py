from __future__ import annotations

import os
import time
from typing import Any, List

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build

from gcpfire.instance import Instance, InstanceSpecBuilder
from gcpfire.keys import generate_keypair, write_privatekey
from gcpfire.logger import logger

from .job import JobSpec

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
HARD_LIMIT_MAX_INSTANCES = 10


def get_credentials() -> service_account.Credentials:
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/compute"]
    )


def get_compute_client() -> Resource:
    logger.debug("Building Compute Client.")
    credentials = get_credentials()
    return build("compute", "v1", credentials=credentials, cache_discovery=False)


class ComputeAPI:
    project: str
    zone: str
    compute: Resource

    def __init__(self, project: str, zone: str) -> None:
        logger.info("Creating Compute API Instance.")
        self.project = project
        self.zone = zone
        self.compute = get_compute_client()

    def get_image_link(self, project: str, family: str) -> Any:
        # TODO: enable global images (currently limited to images from OUR project)
        # Get the latest image
        logger.debug(f"Getting image {family} from project {project}")
        image_response = self.compute.images().getFromFamily(project=project, family=family).execute()
        logger.debug(f"Got {image_response['selfLink']}")
        return image_response["selfLink"]

    def create_instance(self, builder: InstanceSpecBuilder) -> Any:
        logger.info(f"Creating Instance {builder.name}.")
        instance_spec = builder.build(self.project, self.zone)
        request = (
            self.compute.instances().insert(project=self.project, zone=self.zone, body=instance_spec.config).execute()
        )
        result = self.wait_for_response(request["name"])
        return result

    def wait_for_response(self, operation: Any) -> Any:
        logger.info("Waiting for operation to finish...")
        while True:
            result = (
                self.compute.zoneOperations().get(project=self.project, zone=self.zone, operation=operation).execute()
            )

            if result["status"] == "DONE":
                logger.info("done.")
                if "error" in result:
                    errors = result["error"]["errors"]  # nice google!
                    if len(errors) == 1 and errors[0]["code"] == "ZONE_RESOURCE_POOL_EXHAUSTED":
                        raise NoResourcesError(errors[0]["message"])  # try to map error
                    elif len(errors) == 1:
                        raise Exception(errors[0]["message"])  # it's unknown so we raise a generic error
                    else:
                        raise Exception(result["error"])  # multiple errors(?)
                else:
                    return result

            time.sleep(1)

    def list_instances(self) -> Any:
        result = self.compute.instances().list(project=self.project, zone=self.zone).execute()
        return result["items"] if "items" in result else None

    def update_external_ip(self, instance: Instance) -> None:
        logger.debug(f"Getting instance {instance.name} data.")
        request_instance_get = (
            self.compute.instances().get(project=self.project, zone=self.zone, instance=instance.name).execute()
        )
        if request_instance_get is not None:
            logger.debug("Instance metadata:\n" + str(request_instance_get["metadata"]))
            external_ip = request_instance_get["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
            logger.info(f"Instance {instance.name} external ip is {external_ip}")
            instance.external_ip = external_ip

    def add_ssh_keys(self, instance: Instance, username: str = "gcpfire") -> None:
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
            priv, pub = generate_keypair(username)
            private_key_file = write_privatekey(priv, instance.name, outpath=os.path.join(os.getcwd(), "secrets"))
            logger.info(f"Private key file available at: {private_key_file}")

            keys.append(f"{username}:{pub.decode()}")

            body = {"items": [{"key": "ssh-keys", "value": "\n".join(keys)}, *other_items], "fingerprint": fingerprint}

            logger.info(f"Adding public key to Instance (user:{username})...")
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

    def delete_instance(self, instance: Instance) -> Any:
        logger.info(f"Deleting Instance {instance.name}")
        return self.compute.instances().delete(project=self.project, zone=self.zone, instance=instance.name).execute()

    def cleanup(self, instance: Instance, wait: bool) -> None:
        if wait:
            input(f"DELETE instance {instance.name}? [Enter]")
        request = self.delete_instance(instance)
        self.wait_for_response(request["name"])

        instance.delete_local_keyfile()

    def fire(self, job: JobSpec, wait: bool = False, retry_wait: int = 5, max_retry: int = 5) -> List[bytes]:
        image_link = self.get_image_link(self.project, job.image_name)

        builder = InstanceSpecBuilder(
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

        # we could return the instance right here, but for now we will populate the instances directly from the API
        # so we know it really exists. As of now, there is no real benefit of tracking instance states also in gcpfire
        # because we will throw away the instance anyway after executing the next few lines of code.
        self.create_instance(builder)

        instances = self.list_instances()
        if instances is not None:
            logger.info("Instances in project %s and zone %s:" % (self.project, self.zone))
            for instance in instances:
                logger.info(" - " + instance["name"])
        else:
            raise NoInstancesError

        this_instance = Instance(builder.name, self.project, self.zone)
        # self.update_external_ip(this_instance)
        self.add_ssh_keys(this_instance)  # add ssh keys to instance

        try:
            return this_instance.remote_execute_script(
                script_path=job.job_script_path, retry_wait=retry_wait, max_retry=max_retry
            )
        except Exception as e:
            raise e  # capture all errors and re-raise, so we can guarantee the finally is executed no matter which exception happens
        finally:
            self.cleanup(this_instance, wait)


class InstanceNotExistsError(Exception):
    """Requested instance does not exist according to GCP API."""

    pass


class TooManyInstancesError(Exception):
    """More instances are running than we have allowed for this Project"""

    pass


class NoInstancesError(Exception):
    """We have created an instances but GCP reports no instances. This is a FATAL errror and should not happen."""

    pass


class NoResourcesError(Exception):
    """Raised when GCP has no Resources to fulfil our request."""

    pass
