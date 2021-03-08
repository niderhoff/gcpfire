#!/bin/bash
#!/bin/bash
PROJECT_ID=$(curl http://metadata/computeMetadata/v1/instance/attributes/project_id -H "Metadata-Flavor: Google")
INPUT_URI=$(curl http://metadata/computeMetadata/v1/instance/attributes/input_uri -H "Metadata-Flavor: Google")
INPUT_URI=$(curl http://metadata/computeMetadata/v1/instance/attributes/output_uri -H "Metadata-Flavor: Google")
RALLIES_URI=$(curl http://metadata/computeMetadata/v1/instance/attributes/rallies_uri -H "Metadata-Flavor: Google")
IMAGE_NAME="gcr.io/$PROJECT_ID/exporter:latest"
mkdir -p tmp/cache
mkdir -p tmp/output
docker pull "$IMAGE_NAME"
time docker run \
    --rm \
    --gpus all \
    --name exporter \
    --mount type=bind,source="$(pwd)"/tmp/cache,target=/cache \
    --mount type=bind,source="$(pwd)"/tmp/output,target=/output \
    "$IMAGE_NAME" \
    "$INPUT_URI" \
    "$OUTPUT_URI" \
    "$RALLIES_URI"