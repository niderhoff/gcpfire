#!/bin/bash
PROJECT_ID=$(curl http://metadata/computeMetadata/v1/instance/attributes/project_id -H "Metadata-Flavor: Google")
INPUT_URI=$(curl http://metadata/computeMetadata/v1/instance/attributes/input_uri -H "Metadata-Flavor: Google")
OUTPUT_URI=$(curl http://metadata/computeMetadata/v1/instance/attributes/output_uri -H "Metadata-Flavor: Google")
mkdir -p /tmp/cache
mkdir -p /tmp/output
docker pull gcr.io/"$PROJECT_ID"/exporter:latest
time docker run \
    -it \
    --name exporter \
    --mount type=bind,source="$(pwd)"/tmp/cache,target=/cache \
    --mount type=bind,source="$(pwd)"/tmp/output,target=/output \
    exporter:latest \
    "$INPUT_URI" \
    "$OUTPUT_URI"