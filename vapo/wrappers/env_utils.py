# Derived from VREnv/vr_env/utils/utils.py

import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Union

import numpy as np
import quaternion
from scipy.spatial.transform.rotation import Rotation as R

# A logger for this file
logger = logging.getLogger(__name__)


def xyzw_to_wxyz(arr):
    """
    Convert quaternions from pyBullet to numpy.
    """
    return [arr[3], arr[0], arr[1], arr[2]]


def wxyz_to_xyzw(arr):
    """
    Convert quaternions from numpy to pyBullet.
    """
    return [arr[1], arr[2], arr[3], arr[0]]


def nano_sleep(time_ns):
    """
    Spinlock style sleep function. Burns cpu power on purpose
    equivalent to time.sleep(time_ns / (10 ** 9)).

    Should be more precise, especially on Windows.

    Args:
        time_ns: time to sleep in ns

    Returns:

    """
    wait_until = time.time_ns() + time_ns
    while time.time_ns() < wait_until:
        pass


def unit_vector(vector):
    """Returns the unit vector of the vector."""
    return vector / np.linalg.norm(vector)


def angle_between_quaternions(q1, q2):
    """
    Returns the minimum rotation angle between to orientations expressed as quaternions
    quaternions use X,Y,Z,W convention
    """
    q1 = xyzw_to_wxyz(q1)
    q2 = xyzw_to_wxyz(q2)
    q1 = quaternion.from_float_array(q1)
    q2 = quaternion.from_float_array(q2)

    theta = 2 * np.arcsin(np.linalg.norm((q1 * q2.conjugate()).vec))
    return theta


def angle_between(v1, v2):
    """Returns the angle in radians between vectors 'v1' and 'v2'::

    >>> angle_between((1, 0, 0), (0, 1, 0))
    1.5707963267948966
    >>> angle_between((1, 0, 0), (1, 0, 0))
    0.0
    >>> angle_between((1, 0, 0), (-1, 0, 0))
    3.141592653589793
    """
    v1_u = unit_vector(v1)
    v2_u = unit_vector(v2)
    return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))


class EglDeviceNotFoundError(Exception):
    """Raised when EGL device cannot be found"""


def get_egl_device_id(cuda_id: int) -> Union[int]:
    """
    >>> i = get_egl_device_id(0)
    >>> isinstance(i, int)
    True
    """
    assert isinstance(cuda_id, int), "cuda_id has to be integer"
    dir_path = Path(__file__).absolute().parents[2] / "egl_check"
    if not os.path.isfile(dir_path / "EGL_options.o"):
        if os.environ.get("LOCAL_RANK", "0") == "0":
            print("Building EGL_options.o")
            subprocess.call(["bash", "build.sh"], cwd=dir_path)
        else:
            # In case EGL_options.o has to be built and multiprocessing is used, give rank 0 process time to build
            time.sleep(5)
    result = subprocess.run(["./EGL_options.o"], capture_output=True, cwd=dir_path)
    n = int(result.stderr.decode("utf-8").split(" of ")[1].split(".")[0])
    for egl_id in range(n):
        my_env = os.environ.copy()
        my_env["EGL_VISIBLE_DEVICE"] = str(egl_id)
        result = subprocess.run(["./EGL_options.o"], capture_output=True, cwd=dir_path, env=my_env)
        match = re.search(r"CUDA_DEVICE=[0-9]+", result.stdout.decode("utf-8"))
        if match:
            current_cuda_id = int(match[0].split("=")[1])
            if cuda_id == current_cuda_id:
                return egl_id
    raise EglDeviceNotFoundError


def angle_between_angles(a, b):
    diff = b - a
    return (diff + np.pi) % (2 * np.pi) - np.pi


def to_relative_action(actions, robot_obs, max_pos=0.02, max_orn=0.05):
    assert isinstance(actions, np.ndarray)
    assert isinstance(robot_obs, np.ndarray)

    rel_pos = actions[:3] - robot_obs[:3]
    rel_pos = np.clip(rel_pos, -max_pos, max_pos) / max_pos

    rel_orn = angle_between_angles(robot_obs[3:6], actions[3:6])
    rel_orn = np.clip(rel_orn, -max_orn, max_orn) / max_orn

    gripper = actions[-1:]
    return np.concatenate([rel_pos, rel_orn, gripper])


def set_egl_device(device):
    assert "EGL_VISIBLE_DEVICES" not in os.environ, "Do not manually set EGL_VISIBLE_DEVICES"
    try:
        cuda_id = device.index if device.type == "cuda" else 0
    except AttributeError:
        cuda_id = device
    try:
        egl_id = get_egl_device_id(cuda_id)
    except EglDeviceNotFoundError:
        logger.warning(
            "Couldn't find correct EGL device. Setting EGL_VISIBLE_DEVICE=0. "
            "When using DDP with many GPUs this can lead to OOM errors. "
            "Did you install PyBullet correctly? Please refer to VREnv README"
        )
        egl_id = 0
    os.environ["EGL_VISIBLE_DEVICES"] = str(egl_id)
    logger.info(f"EGL_DEVICE_ID {egl_id} <==> CUDA_DEVICE_ID {cuda_id}")


def pos_orn_to_matrix(pos, orn):
    """
    :param pos: np.array of shape (3,)
    :param orn: np.array of shape (4,) -> quaternion xyzw
                np.quaternion -> quaternion wxyz
                np.array of shape (3,) -> euler angles xyz
    :return: 4x4 homogeneous transformation
    """
    mat = np.eye(4)
    if isinstance(orn, np.quaternion):
        orn = np_quat_to_scipy_quat(orn)
        mat[:3, :3] = R.from_quat(orn).as_matrix()
    elif len(orn) == 4:
        mat[:3, :3] = R.from_quat(orn).as_matrix()
    elif len(orn) == 3:
        mat[:3, :3] = R.from_euler("xyz", orn).as_matrix()
    mat[:3, 3] = pos
    return mat


def orn_to_matrix(orn):
    mat = np.eye(3)
    if isinstance(orn, np.quaternion):
        orn = np_quat_to_scipy_quat(orn)
        mat[:3, :3] = R.from_quat(orn).as_matrix()
    elif len(orn) == 4:
        mat[:3, :3] = R.from_quat(orn).as_matrix()
    elif len(orn) == 3:
        mat[:3, :3] = R.from_euler("xyz", orn).as_matrix()
    return mat


def np_quat_to_scipy_quat(quat):
    """wxyz to xyzw"""
    return np.array([quat.x, quat.y, quat.z, quat.w])


if __name__ == "__main__":
    import doctest

    doctest.testmod()
