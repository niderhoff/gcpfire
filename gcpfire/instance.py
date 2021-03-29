from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from gcpfire import ssh_client as ssh
from gcpfire.keys import delete_key_file
from gcpfire.logger import logger


class Instance:
    """Define a new Instance."""

    external_ip: Optional[str] = None
    private_key_file: Optional[str] = None

    def __init__(self, name: str, project: str, zone: str) -> None:
        self.name = name
        self.project = project
        self.zone = zone

    def delete_local_keyfile(self) -> None:
        if self.private_key_file is not None:
            delete_key_file(self.private_key_file)
            self.private_key_file = None

    def remote_execute_script(self, script_path: str, retry_wait: int = 5, max_retry: int = 5) -> List[bytes]:
        """Remotely execute code over SSH. Raises Exception if SSH command failed, otherwise returns the stdout or an
           empty list.

        Args:
            script_path (str): path to a bash script we want to remotely execute.
            retry_wait (int, optional): Seconds to wait between retries. Defaults to 5.
            max_retry (int, optional): Retry ssh commands if they fail. Defaults to 5.

        Raises:
            ValueError: path to private key file is empty.
            RemoteExecutionError: Raised if execution failed after #retries. Attaches stderr.

        Returns:
            List[bytes]: Stdout (if any). Will be empty for ssh copy.
        """
        assert self.external_ip is not None

        if script_path is None:
            raise ValueError("No script is given: prohibiting trivial remote code execution.")

        key = self.private_key_file
        if key is None:
            raise ValueError("Need to add a ssh-keys to the Instance before code can be executed.")

        # Because we reuse an IP for different instances we have to remove it from ~/.ssh/known_hosts.
        # However, we have to manually remove it because openssh does not allow us to disable KnownHostsFile anymore.
        ssh.remove_from_known_hosts(self.external_ip)

        # For some reason the connection does not work on the first try. Maybe because google only adds the key to
        # authorized_keys during the first connection attempt. So we just keep probing the connection a couple times.
        for _ in range(max_retry):
            try:
                # Test connection to trigger a retry if the ssh key is not ready on the remote.
                ssh.test_connection(self.external_ip, key)

                # Otherwise we can continue (but we can still get a ssh.RemoteExecutionError with the next commands)
                # Ok it worked, we can now upload a bash file and execute it.
                ssh.ssh_copy_file(self.external_ip, script_path, key)

                # We need full login-shell (`bash -l`) or otherwise Compute Engine login agent will not automatically grant
                # us the access scopes from the service account and we cannot access the Container Registry
                return ssh.ssh_run_command(self.external_ip, f"bash -l {os.path.basename(script_path)}", key)
            except ssh.ShellExecutionError as e:
                err = e
                # if we had an error we will wait and skip ahead to next iteration
                time.sleep(retry_wait)
                continue
        else:  # loop did not exit early (no break) --> we exhausted our # of tries and will propagate stderr
            raise RemoteExecutionError(err.message, err.stderror)


class RemoteExecutionError(ssh.ShellExecutionError):
    """Indicates an Exception during remote code execution. Option to attach stderror byte buffer."""


class InstanceSpecBuilder:
    """We use a builder pattern, because we want to have an Instance template we can apply to several ZONES
    simultaneously. So we have to finalize the spec right before creation of the instance, depending of the zone the
    compute api instance is attached to.
    """

    serial_port_enable = False
    oslogin_enable = False

    def __init__(
        self,
        name: str,
        image_link: str,
        additional_meta: List[Dict[str, Any]],
        machine_type: str,
        accelerators: Dict[str, int] = {},
        preemptible: bool = True,
        startup_script_path: Optional[str] = None,
    ) -> None:
        self.name = name
        self.additional_meta = additional_meta
        self.image_link = image_link
        self.machine_type = machine_type
        self.gpus = accelerators
        self.preemptible = preemptible
        self.startup_script_path = startup_script_path

    def build(self, project: str, zone: str) -> InstanceSpecBuilder:
        """Finalizes the spec with PROJECT and ZONE information and builds the config."""
        logger.debug(
            (
                f"Creating Instance {self.name} with machine_type={self.machine_type}, preemptible={self.preemptible}, "
                f"gpus={self.gpus}, startup_script={self.startup_script_path}, metadata={self.additional_meta}"
            )
        )
        if self.preemptible:
            logger.debug("This instance is pre-emptible and will live for no longer than 24 hours.")

        # Image
        source_disk_image = self.image_link

        # Configure the Machine
        machine_type = "zones/%s/machineTypes/%s" % (zone, self.machine_type)

        # Configure the Accelerators
        guest_accelerators = []
        if len(self.gpus) > 0:
            for label, count in self.gpus.items():
                accelerator_type = "projects/%s/zones/%s/acceleratorTypes/%s" % (
                    project,
                    zone,
                    label,
                )
                guest_accelerators.append({"acceleratorCount": count, "acceleratorType": accelerator_type})

        meta_items = [
            {"key": "serial-port-enable", "value": self.serial_port_enable},
            {"key": "enable-oslogin", "value": self.oslogin_enable},
            *self.additional_meta,
        ]

        if self.startup_script_path is not None:
            startup_script = open(self.startup_script_path, "r").read()
            meta_items.append(
                # Automatically install the driver after start-up
                # (not needed for us since we have it already installed in the disk image)
                # {"key": "install-nvidia-driver", "value": True},
                {
                    # Startup script is automatically executed by the
                    # instance upon startup.
                    "key": "startup-script",
                    "value": startup_script,
                }
            )

        self.config = {
            "name": self.name,
            "machineType": machine_type,
            "scheduling": {
                "preemptible": self.preemptible,
                "onHostMaintenance": "TERMINATE",
                "automaticRestart": False,
            },
            # Specfiy the boot disk and the image to use asa source
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "diskSizeGb": "50",
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
                    # "email": "gcpfire-worker@main-composite-287415.iam.gserviceaccount.com",
                    "email": "default",
                    "scopes": [
                        "https://www.googleapis.com/auth/devstorage.read_write",
                        "https://www.googleapis.com/auth/logging.write",
                        "https://www.googleapis.com/auth/datastore",
                        "https://www.googleapis.com/auth/monitoring.write",
                        "https://www.googleapis.com/auth/service.management.readonly",
                        "https://www.googleapis.com/auth/servicecontrol",
                        "https://www.googleapis.com/auth/trace.append",
                    ],
                }
            ],
            # Metadata is readable from the instance and allows you to pass
            # configuration from deployment scripts to instance
            "metadata": {"items": meta_items},
        }

        return self
