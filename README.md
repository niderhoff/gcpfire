# GCP Fire

## Next Steps

- [ ] Reduce Docker Image download time by having some version of the docker images that is semi-recent baked into the image.
- [ ] Use optional git pull & default image instead of Docker to reduce runtime.
- [ ] PIPE SSH Key
- [ ] Add Profiling
- [ ] Run Multiple Jobs in Succession
- [ ] Parallelize & Proper parallelized logging
- [ ] Get rid of "Any" type hints from Google API

## Changelog

### 0.2.1

- [x] Better error handling and propagation of stdout/stderr.

### 0.2.0

- [x] Add Type hints
- [x] Minor improvements

### 0.1.1

- [x] Make this a package (so we can import it on other packages)
- [x] Add Exporter Task
- [x] Docker uses GPU now
- [x] Analysis Task is now working.
- [x] Set proper service account & make SSH-Login inherit permissions.
- [x] Enabble Docker Client on VM access to docker registry.

### 0.1.0

- [x] Disable Serial Port
- [x] Custom Image incl. driver and all code to have better startup times
- [x] Split process (analyze + export into 2 parts)
- [x] Add Remote Code Execution to run the script
- [x] Propagate error code up
