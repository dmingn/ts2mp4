import subprocess
from typing import Any, Literal, Union, overload

from logzero import logger


@overload
def execute_command(
    command: list[str], text: Literal[True] = True
) -> subprocess.CompletedProcess[str]: ...


@overload
def execute_command(
    command: list[str], text: Literal[False]
) -> subprocess.CompletedProcess[bytes]: ...


def execute_command(
    command: list[str], text: bool = True
) -> Union[subprocess.CompletedProcess[str], subprocess.CompletedProcess[bytes]]:
    """Executes a given command and returns the result.

    Args:
        command: A list of strings representing the command to execute.
        text: If True, decode stdout and stderr as text.

    Returns:
        A CompletedProcess object with the results of the command.
    """
    logger.info(f"Running command: {' '.join(command)}")
    run_kwargs: dict[str, Any] = {"capture_output": True, "check": False}
    if text:
        run_kwargs["text"] = True
        run_kwargs["encoding"] = "utf-8"
        run_kwargs["errors"] = "replace"

    result = subprocess.run(command, **run_kwargs)

    if text:
        if result.stdout:
            logger.info(result.stdout)
        if result.stderr:
            logger.error(result.stderr)
    else:
        # Assuming binary output might not be useful to log directly
        pass
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result
