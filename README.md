# GCP Fire

## Next Steps

- [ ] Use optional git pull & default image instead of Docker to reduce runtime.
- [ ] Make this a package
- [ ] PIPE SSH Key
- [ ] Add Profiling
- [ ] Run Multiple Jobs in Succession
- [ ] Parallelize & Proper parallelized logging
- [ ] Add Type hints

## Changelog

### 0.1.1

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
