"""Very basic ssh client"""
import os
import shutil
import subprocess

from gcpfire.logger import logger


def check_command_exists(executable):
    if shutil.which(executable) is None:
        raise FileNotFoundError("ssh client is not installed?")


def test_connection(host, keyfile, user="gcpfire"):
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(f"{user}@{host}")
    cmd.append("echo 1")
    invoke_line(cmd)


def ssh_copy_file(host, filepath, keyfile, user="gcpfire"):
    cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(filepath)
    fname = os.path.basename(filepath)
    cmd.append(f"{user}@{host}:~/{fname}")
    invoke_line(cmd)


def ssh_run_command(host, remote_cmd, keyfile, force_tty=True, user="gcpfire"):
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    if force_tty:
        cmd.append("-t")
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)
    invoke_line(cmd)


class RemoteExecutionError(Exception):
    pass


def invoke_line(cmd):
    check_command_exists(cmd[0])
    logger.debug("Running command: " + " ".join(cmd))
    ssh = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = ssh.stdout.readlines()
    if result == []:
        stderr = [line for line in ssh.stderr.readlines() if not line.startswith(b"Warning")]
        if len(stderr) > 0:
            logger.error("ERROR: %s" % stderr)
            raise RemoteExecutionError("ERROR: %s" % stderr)
        return 0
    else:
        logger.debug(result)
        result


def remove_host(ip):
    cmd = ["ssh-keygen", "-f", "~/.ssh/known_hosts", "-R", "%s" % ip]
    logger.debug(f"Running command: {cmd}")
    # we don't care about the result here
    subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
