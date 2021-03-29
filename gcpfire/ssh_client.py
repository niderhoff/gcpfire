"""Very basic ssh client"""
import os
import shutil
import subprocess
from typing import List, Optional

from gcpfire.logger import logger


def check_command_exists(executable: str) -> None:
    """Check if the executable name is present in PATH.

    Args:
        executable (str): executable name

    Raises:
        FileNotFoundError: raised if executable is not present in path.
    """
    if shutil.which(executable) is None:
        raise FileNotFoundError("ssh client is not installed?")


def remove_from_known_hosts(hostname: str) -> None:
    """Removes the ip from ssh know_hosts file. This is necessary because we reuse IPs a lot with different keys
    attached to them and some versions of ssh don't respect the disabling of StrictHostKeyChecking.

    Args:
        hostname (str): remote hostname
    """
    cmd = ["ssh-keygen", "-f", "~/.ssh/known_hosts", "-R", "%s" % hostname]
    logger.debug(f"Running command: {cmd}")
    # we don't care about the result here
    subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_connection(host: str, keyfile: Optional[str], user: str = "gcpfire") -> List[bytes]:
    """Run a simple command on the remote host to check ssh connection. We just want to propagate the exception of
    invoke_line() so we can initiate a retry if the ssh connection is not ready.

    Args:
        host (str): remote hostname
        keyfile (Optional[str]): ssh key for login
        user (str, optional): remote user name. Defaults to "gcpfire".

    Raises:
        ShellExecutionError: invoke_line raises this error if stderr is present. Contains the stderr buffer.

    Returns:
        List[bytes]: stdout
    """
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(f"{user}@{host}")
    cmd.append("echo 1")
    return invoke_line(cmd)


def ssh_copy_file(host: str, filepath: str, keyfile: Optional[str], user: str = "gcpfire") -> List[bytes]:
    """Copy a file over ssh.

    Args:
        host (str): remote hostname
        filepath (str): local path of the file (on the client side)
        keyfile (str): private key for login
        user (str, optional): remote user name. Defaults to "gcpfire".

    Returns:
        List[bytes]: stdout (if present)
    """
    cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    cmd.append(filepath)
    fname = os.path.basename(filepath)
    cmd.append(f"{user}@{host}:~/{fname}")
    return invoke_line(cmd)


def ssh_run_command(
    host: str, remote_cmd: str, keyfile: Optional[str], force_tty: bool = True, user: str = "gcpfire"
) -> List[bytes]:
    """Run a command on the remote machine over ssh.

    Args:
        host (str): remote hostname
        remote_cmd (str): command for remote execution
        keyfile (str): private key file for login
        force_tty (bool, optional): Force allocation of pseudo-tty so we can invoke a full environment. Defaults to True.
        user (str, optional): remote user name. Defaults to "gcpfire".

    Raises:
        ShellExecutionError: invoke_line raises this error if stderr is present. Contains the stderr buffer.

    Returns:
        List[bytes]: stdout (if present)
    """
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if keyfile is not None:
        cmd.extend(["-i", keyfile])
    if force_tty:
        cmd.append("-t")
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)
    return invoke_line(cmd)


class ShellExecutionError(Exception):
    """Indicates an Exception during invoke_line() with option to attach stderror byte buffer."""

    def __init__(self, message: Optional[str] = None, stderror: Optional[List[bytes]] = None):
        self.message = message
        self.stderror = stderror

    def __str__(self) -> str:
        if self.message is not None:
            return self.message
        else:
            return "Error during Remote Execution."


def invoke_line(cmd: List[str], strict: bool = False) -> List[bytes]:
    """Runs a shell command in a subprocess.

    Args:
        cmd (List[str]): command string split by spaces
        strict (bool): will consider warnings as errors if true.

    Raises:
        ShellExecutionError: raised if stderr is present. Contains the stderr buffer.

    Returns:
        List[bytes]: stdout (if present)
    """
    check_command_exists(cmd[0])
    logger.debug("Running command: " + " ".join(cmd))
    ssh = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ssh.stdout is not None:
        result = ssh.stdout.readlines()
    if result == []:
        if ssh.stderr is not None:
            # only fail for fatal errors
            stderr = [line for line in ssh.stderr.readlines() if (not line.startswith(b"Warning") or strict)]
            if len(stderr) > 0:
                logger.error("ERROR: %s" % stderr)
                raise ShellExecutionError("ERROR: %s" % stderr, stderr)
    else:
        logger.debug(result)
    return result
