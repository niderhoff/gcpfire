from gcpfire.logger import logger

"""Define a new Instance"""


class InstanceDefinitionBuilder:
    def __init__(self, name, image_link, meta, machine_type, accelerators={}, preemptible=True, script_path=None):
        self.name = name
        self.additional_meta = meta
        self.image_link = image_link
        self.machine_type = machine_type
        self.gpus = accelerators
        self.preemptible = preemptible
        self.script_path = script_path

    def build(self, project, zone):
        """create instance with <name> and access to a certain gs <bucket>"""
        logger.debug(
            (
                f"Creating Instance {self.name} with machine_type={self.machine_type}, preemptible={self.preemptible}, "
                f"gpus={self.gpus}, script={self.script_path}, metadata={self.additional_meta}"
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

        if self.script_path is not None:
            startup_script = open(self.script_path, "r").read()

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
                    *self.additional_meta,
                ]
            },
        }
