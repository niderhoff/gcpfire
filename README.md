# GCP Fire

## Next Steps

- [ ] Docker Client on Container needs access to docker registry
- [ ] Get Status Code from startup script command and delete instance automaticall if successful & if not successful (instead of manual wait=true)
  - [ ] Read VM Logs
  - [ ] Write Logs <https://cloud.google.com/logging/docs/setup/python>
- [ ] propagate error code up
- [ ] Run Multiple Jobs in Succession
- [ ] Parallelize
- [ ] Caution: The interactive serial console does not support IP-based access restrictions such as IP allowlists. If you enable the interactive serial console on an instance, clients can attempt to connect to that instance from any IP address. Anybody can connect to that instance if they know the correct SSH key, username, project ID, zone, and instance name. Use firewall rules to control access to your network and specific ports.
- [x] Custom Image incl. driver and all code to have better startup times
- [x] split process (analyze + export into 2 parts)
