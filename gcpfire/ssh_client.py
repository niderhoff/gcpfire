"""Very basic ssh client"""
import os
import shutil
import subprocess
from typing import List

from gcpfire.logger import logger


def check_command_exists(executable: str) -> None:
    if shutil.which(executable) is None:
        raise FileNotFoundError("ssh client is not installed?")


def test_connection(host: str, keyfile: str, user: str = "gcpfire") -> List[bytes]:
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(f"{user}@{host}")
    cmd.append("echo 1")
    return invoke_line(cmd)


def ssh_copy_file(host: str, filepath: str, keyfile: str, user: str = "gcpfire") -> List[bytes]:
    cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(filepath)
    fname = os.path.basename(filepath)
    cmd.append(f"{user}@{host}:~/{fname}")
    return invoke_line(cmd)


def ssh_run_command(
    host: str, remote_cmd: str, keyfile: str, force_tty: bool = True, user: str = "gcpfire"
) -> List[bytes]:
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    if force_tty:
        cmd.append("-t")
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)
    return invoke_line(cmd)


class RemoteExecutionError(Exception):
    pass


def invoke_line(cmd: List[str]) -> List[bytes]:
    check_command_exists(cmd[0])
    logger.debug("Running command: " + " ".join(cmd))
    ssh = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ssh.stdout is not None:
        result = ssh.stdout.readlines()
    if result == []:
        if ssh.stderr is not None:
            stderr = [line for line in ssh.stderr.readlines() if not line.startswith(b"Warning")]
            if len(stderr) > 0:
                logger.error("ERROR: %s" % stderr)
                raise RemoteExecutionError("ERROR: %s" % stderr)
    else:
        logger.debug(result)
    return result


def remove_host(ip: str) -> None:
    cmd = ["ssh-keygen", "-f", "~/.ssh/known_hosts", "-R", "%s" % ip]
    logger.debug(f"Running command: {cmd}")
    # we don't care about the result here
    subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
