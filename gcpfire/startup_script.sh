#!/bin/bash
#apt-get update
#apt-get -y install 

#sudo /opt/deeplearning/install-driver.sh
# should be done by GCP automatically

#IMAGE_URL=$(curl http://metadata/computeMetadata/v1/instance/attributes/url -H "Metadata-Flavor: Google")
DOCKER_IMAGE=$(curl http://metadata/computeMetadata/v1/instance/attributes/docker_image -H "Metadata-Flavor: Google")
CS_BUCKET=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")
docker pull "$DOCKER_IMAGE"
time docker run -it liimba/aio:latest "$CS_BUCKET"