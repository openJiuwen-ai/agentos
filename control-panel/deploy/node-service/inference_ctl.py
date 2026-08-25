#!/usr/bin/env python3
# coding: utf-8
"""
Inference Service Control - simplified start/stop/config for MindIE Motor vLLM deployment.

Usage:
    python3 inference_ctl.py start  --weight-path /path/to/weights --model-path /path/to/model --model-name deepseek-r1
    python3 inference_ctl.py stop
    python3 inference_ctl.py status
    python3 inference_ctl.py config --show
    python3 inference_ctl.py config --model-name new-model-name --npu-num 8
    python3 inference_ctl.py check  --weight-path /path/to/weights --model-path /path/to/model
"""

import argparse
import glob
import json
import logging
import os
import platform
import re
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger("node-service.inference_ctl")
CONFIG_DIR = os.path.join(SCRIPT_DIR, "config")
STATE_DIR = os.path.expanduser("~/.ascend_deployer/vllm_service")
CONTAINER_NAME = "single_container"
USER_CONFIG = os.path.join(STATE_DIR, "user_config.json")
ENV_CONFIG = os.path.join(CONFIG_DIR, "env.json")


# ── helpers ──────────────────────────────────────────────────────────────

def run_cmd(cmd, check=False):
    """Run a shell command, return (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, text=True, capture_output=True, shell=isinstance(cmd, str))
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\n{r.stderr.strip()}")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── NPU detection ────────────────────────────────────────────────────────

def detect_hardware_type():
    """Detect hardware type from npu-smi."""
    logger.info("detecting hardware type ...")
    rc, out, _ = run_cmd("npu-smi info -m")
    if rc != 0:
        raise RuntimeError("npu-smi not available")

    if "A3" in out or "910" in out:
        return "800I_A3"
    elif "A2" in out or "310" in out:
        return "850-Atlas-8p-8"
    else:
        raise RuntimeError(f"unsupported hardware:\n{out}")


def detect_available_npus(hardware_type):
    """Return list of available (idle) NPU card IDs."""
    rc, out, _ = run_cmd("npu-smi info -m")
    if rc != 0:
        return []

    available = []
    for line in out.splitlines():
        if "Ascend" not in line:
            continue
        card_id = int(line.split()[0])

        if hardware_type == "800I_A3":
            rc0, out0, _ = run_cmd(f"npu-smi info -t proc-mem -i {card_id} -c 0")
            rc1, out1, _ = run_cmd(f"npu-smi info -t proc-mem -i {card_id} -c 1")
            c0_ok = rc0 == 0 and "Process id:" not in out0
            c1_ok = rc1 == 0 and "Process id:" not in out1
            if c0_ok and c1_ok:
                available.append(card_id)
        else:
            rc2, out2, _ = run_cmd(f"npu-smi info -t proc-mem -i {card_id}")
            if rc2 == 0 and "Process id:" not in out2:
                available.append(card_id)

    return available


def default_npu_num(hardware_type):
    return 16 if hardware_type == "800I_A3" else 4


# ── image resolution ─────────────────────────────────────────────────────

def resolve_vllm_image(user_image_name, resources_dir):
    """Resolve vLLM image: use user-specified name or auto-load from resources."""
    if user_image_name:
        return user_image_name

    arch_raw = platform.machine().lower()
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(arch_raw, arch_raw)
    search_dir = os.path.join(resources_dir, "pymotor-image", arch)

    if not os.path.isdir(search_dir):
        raise RuntimeError(f"image directory not found: {search_dir}")

    candidates = []
    for ext in ("*.tar", "*.tar.gz"):
        candidates.extend(glob.glob(os.path.join(search_dir, f"mindie-motor*{ext}")))

    if not candidates:
        raise RuntimeError(f"no mindie-motor image found in {search_dir}")

    candidates.sort(key=os.path.getmtime, reverse=True)
    tar_path = candidates[0]
    logger.info("loading image from %s ...", tar_path)
    rc, out, err = run_cmd(f"docker load -i {tar_path}", check=True)
    for line in out.splitlines():
        m = re.search(r"Loaded image:\s*(\S+)", line)
        if m:
            logger.info("loaded image: %s", m.group(1))
            return m.group(1)

    raise RuntimeError(f"failed to parse image name from docker load output:\n{out}")


# ── startup file extraction ──────────────────────────────────────────────

def extract_startup_files(image_name, dest_dir):
    """Extract boot scripts from the MindIE Motor image."""
    os.makedirs(dest_dir, exist_ok=True)
    tmp = "tmp_vllm_extract"

    logger.info("creating temp container from %s ...", image_name)
    rc, _, err = run_cmd(f"docker create --name {tmp} {image_name}")
    if rc != 0:
        raise RuntimeError(f"docker create failed: {err}")
    try:
        files = ["boot.sh", "common.sh", "hccl_tools.py", "set_env_docker.py"]
        for f in files:
            src = f"{tmp}:/tmp/motor/examples/deployer/startup/{f}"
            logger.info("extracting %s ...", f)
            rc, _, err = run_cmd(f"docker cp {src} {dest_dir}/")
            if rc != 0:
                raise RuntimeError(f"docker cp {f} failed: {err}")

        logger.info("extracting roles/ ...")
        rc, _, err = run_cmd(f"docker cp {tmp}:/tmp/motor/examples/deployer/startup/roles/. {dest_dir}/")
        if rc != 0:
            raise RuntimeError(f"docker cp roles/ failed: {err}")
        logger.info("extracting lib/ ...")
        rc, _, err = run_cmd(f"docker cp {tmp}:/tmp/motor/examples/deployer/lib {dest_dir}/")
        if rc != 0:
            raise RuntimeError(f"docker cp lib/ failed: {err}")
    finally:
        run_cmd(f"docker rm -f {tmp}", check=False)


# ── config management ────────────────────────────────────────────────────

ENGINE_DEFAULTS = {
    "gpu_memory_utilization": 0.9,
    "tensor_parallel_size": 1,
    "data_parallel_size": 1,
    "enable_expert_parallel": False,
    "max-model-len": 131072,
    "max-num-batched-tokens": 10240,
    "max-num-seqs": 64,
    "enforce-eager": True,
    "tokenizer-mode": "auto",
    "tool-call-parser": None,
    "reasoning-parser": None,
    "trust-remote-code": True,
    "safetensors-load-strategy": "prefetch",
    "async-scheduling": True,
    "enable-auto-tool-choice": False,
    "seed": 1024,
    "api-server-count": 1,
    "data_parallel_rpc_port": 9000,
    "speculative-config": None,
    "compilation_config": {},
    "model-loader-extra-config": {},
    "additional-config": {},
}


def build_user_config(params, hardware_type, npu_num):
    """Build user_config.json directly from params, no template dependency."""
    # Engine config: merge user params over defaults
    ec = dict(ENGINE_DEFAULTS)
    for key in ec:
        if key in params and params[key] is not None:
            ec[key] = params[key]
    ec["served_model_name"] = params.get("model_name", "")
    ec["model"] = params.get("model_path", "")
    ec["data_parallel_size"] = params.get("data_parallel_size") or npu_num

    # Ensure booleans are proper JSON booleans
    for key in ("enable_expert_parallel", "enforce-eager", "trust-remote-code",
                 "async-scheduling", "enable-auto-tool-choice"):
        if key in ec:
            ec[key] = bool(ec[key])

    if hardware_type == "800I_A3" and "quantization" not in params:
        ec["quantization"] = "ascend"
    elif "quantization" in params and params["quantization"]:
        ec["quantization"] = params["quantization"]

    # Assemble full config
    config = {
        "version": "v2.0",
        "motor_deploy_config": {
            "deploy_mode": "single_container",
            "hybrid_instances_num": 1,
            "single_hybrid_instance_pod_num": 1,
            "hybrid_pod_npu_num": npu_num,
            "image_name": params.get("image_name", ""),
            "job_id": "mindie-motor",
            "hardware_type": hardware_type,
            "weight_mount_path": params.get("weight_path", ""),
        },
        "motor_controller_config": {
            "api_config": {
                "controller_api_port": params.get("controller_port", 2026),
            }
        },
        "motor_coordinator_config": {
            "api_config": {
                "coordinator_api_infer_port": params.get("coordinator_infer_port", 1025),
                "coordinator_api_mgmt_port": params.get("coordinator_mgmt_port", 1030),
                "coordinator_obs_port": params.get("coordinator_obs_port", 1029),
            }
        },
        "motor_engine_union_config": {
            "engine_type": "vllm",
            "motor_nodemanger_config": {
                "api_config": {
                    "node_manager_port": params.get("node_manager_port", 3026),
                },
                "endpoint_config": {
                    "base_port": params.get("base_port", 10000),
                    "mgmt_ports": [],
                    "service_ports": [],
                },
            },
            "engine_config": ec,
        },
    }
    return config


def apply_env_config(dest_dir):
    """Run set_env_docker.py to inject environment variables."""
    script = os.path.join(dest_dir, "set_env_docker.py")
    if os.path.exists(script):
        rc, _, err = run_cmd(f"python3 {script} --configmap_path {dest_dir}")
        if rc != 0:
            raise RuntimeError(f"set_env_docker.py failed: {err}")


def cleanup_old_env_functions(dest_dir):
    """Remove stale set_xxx_env() functions from shell scripts."""
    patterns = [
        r"/^function set_controller_env()/,/^}/d",
        r"/^function set_coordinator_env()/,/^}/d",
        r"/^function set_union_env()/,/^}/d",
        r"/^function set_common_env()/,/^}/d",
        r"/^function set_prefill_env()/,/^}/d",
        r"/^function set_decode_env()/,/^}/d",
        r"/^function set_encode_env()/,/^}/d",
        r"/^function set_kv_pool_env()/,/^}/d",
        r"/^function set_kv_conductor_env()/,/^}/d",
    ]
    targets = ["controller.sh", "coordinator.sh", "engine.sh",
               "common.sh", "all_combine_in_single_container.sh"]

    for target in targets:
        path = os.path.join(dest_dir, target)
        if not os.path.exists(path):
            continue
        for pat in patterns:
            run_cmd(["sed", "-i", pat, path])

    # clean empty lines in common.sh
    common = os.path.join(dest_dir, "common.sh")
    if os.path.exists(common):
        run_cmd(["sed", "-i", "/./,$!d", common])


# ── docker commands ──────────────────────────────────────────────────────

def build_docker_cmd(image_name, config_dir, params, hardware_type, available_npus):
    """Build the docker run command."""
    devices = []
    base_devs = ["/dev/davinci_manager", "/dev/devmm_svm", "/dev/hisi_hdc"]
    for d in base_devs:
        if os.path.exists(d):
            devices.append(f"--device={d}")

    npu_num = params["npu_num"]
    if hardware_type == "850-Atlas-8p-8":
        for i in available_npus[:npu_num]:
            devices.append(f"--device=/dev/davinci{i}")
    else:
        visible = os.environ.get("ASCEND_VISIBLE_DEVICES", "")
        if not visible:
            devs = glob.glob("/dev/davinci[0-9]*")
            ids = [re.findall(r"\d+", d)[0] for d in devs]
            visible = ",".join(ids)
        for i in visible.split(","):
            if i:
                devices.append(f"--device=/dev/davinci{i}")

    weight = params["weight_path"]
    cmd = [
        "docker", "run", "-d",
        "-u", "root",
        "--name", CONTAINER_NAME,
        "--network", "host",
        "-e", "ASCEND_RUNTIME_OPTIONS=NODRV",
        "--privileged=false",
        "--log-driver=json-file",
        "--log-opt", "max-size=50m",
        "--log-opt", "max-file=3",
        "-e", f"CONFIGMAP_PATH={config_dir}",
        "-e", "CONFIG_PATH=/usr/local/Ascend/pyMotor/conf",
        "-e", "ROLE=SINGLE_CONTAINER",
    ]
    cmd.extend(devices)
    cmd.extend([
        "-v", "/usr/local/Ascend/driver:/usr/local/Ascend/driver",
        "-v", "/usr/local/Ascend/add-ons/:/usr/local/Ascend/add-ons/",
        "-v", "/usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi",
        "-v", "/usr/local/sbin:/usr/local/sbin",
        "-v", "/var/log/npu/:/usr/slog",
        "-v", "/mnt:/mnt",
        "-v", f"{config_dir}:{config_dir}",
        "-v", f"{weight}:{weight}:ro",
        image_name,
        "bash", "-c",
        f"export POD_IP=0.0.0.0 && source {config_dir}/boot.sh",
    ])
    return cmd


# ── core operations (reusable by cmd_start and cmd_config) ───────────────

def stop_container():
    """Stop and remove the vLLM container. Returns True if it was running."""
    rc, _, _ = run_cmd(f"docker rm -f {CONTAINER_NAME}")
    if rc == 0:
        logger.info("removed existing container %s", CONTAINER_NAME)
        return True
    return False


def start_from_config(config_path=None, on_progress=None):
    """Read saved config and start container. Used by both cmd_start and cmd_config.

    Args:
        config_path: Path to user_config.json. Defaults to USER_CONFIG.
        on_progress: Optional callback(str) to report progress messages.
    Returns:
        True on success, raises on failure.
    """
    def _log(msg):
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    config_file = config_path or USER_CONFIG
    if not os.path.exists(config_file):
        raise RuntimeError(f"config not found: {config_file}")

    cfg = load_json(config_file)
    dp = cfg["motor_deploy_config"]
    ec = cfg["motor_engine_union_config"]["engine_config"]
    coord = cfg["motor_coordinator_config"]["api_config"]
    ctrl = cfg["motor_controller_config"]["api_config"]
    nm = cfg["motor_engine_union_config"]["motor_nodemanger_config"]["api_config"]

    hw = dp["hardware_type"]
    npu_num = dp["hybrid_pod_npu_num"]
    npus = detect_available_npus(hw)
    _log(f"[INFO] hardware: {hw}, available NPUs: {len(npus)}, requested: {npu_num}")

    if npu_num > len(npus):
        raise RuntimeError(f"need {npu_num} NPUs but only {len(npus)} available")

    image = dp.get("image_name", "")
    if not image:
        raise RuntimeError("image_name not found in config. Run 'start' with --image to set it.")

    # extract startup files
    _log("[INFO] extracting startup files from image ...")
    extract_startup_files(image, STATE_DIR)
    _log("[INFO] startup files extracted")

    params = {
        "weight_path": dp["weight_mount_path"],
        "model_path": ec["model"],
        "model_name": ec["served_model_name"],
        "npu_num": npu_num,
        "controller_port": ctrl["controller_api_port"],
        "coordinator_infer_port": coord["coordinator_api_infer_port"],
        "coordinator_mgmt_port": coord["coordinator_api_mgmt_port"],
        "coordinator_obs_port": coord["coordinator_obs_port"],
        "node_manager_port": nm["node_manager_port"],
    }

    # cleanup + env
    _log("[INFO] cleaning up env functions ...")
    cleanup_old_env_functions(STATE_DIR)
    _log("[INFO] applying env config ...")
    apply_env_config(STATE_DIR)
    _log("[INFO] env config applied")

    # start container
    os.makedirs("/var/log/agentos/agentos-node-service", exist_ok=True)
    _log("[INFO] building docker command ...")
    cmd = build_docker_cmd(image, STATE_DIR, params, hw, npus)
    _log("[INFO] starting container ...")
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"docker run failed: {err}")
    _log(f"[INFO] container started: {out}")

    # wait for ready
    _log("[INFO] waiting for vLLM instance to be ready ...")
    for i in range(20):
        rc, out, _ = run_cmd(f"docker logs --tail 5 {CONTAINER_NAME}")
        if "Instance ready: u0" in out:
            _log("[OK] vLLM instance ready!")
            return True
        time.sleep(30)
        _log(f"[INFO] waiting ... ({(i+1)*30}s)")
        if out:
            for line in out.strip().splitlines()[-3:]:
                _log(f"  > {line}")

    # timeout
    log_path = os.path.join(STATE_DIR, "single_container.log")
    run_cmd(f"docker logs {CONTAINER_NAME} > {log_path} 2>&1")
    raise RuntimeError(f"vLLM failed to start within 10 minutes, full logs saved to {log_path}")


def save_config_from_args(args, image_name):
    """Build and save user_config.json from CLI args. Returns the config dict."""
    hw = detect_hardware_type()
    npu_num = args.npu_num if args.npu_num > 0 else default_npu_num(hw)

    params = {
        "weight_path": os.path.abspath(args.weight_path),
        "model_path": os.path.abspath(args.model_path),
        "model_name": args.model_name,
        "image_name": image_name,
        "controller_port": args.controller_port,
        "coordinator_infer_port": args.coordinator_infer_port,
        "coordinator_mgmt_port": args.coordinator_mgmt_port,
        "coordinator_obs_port": args.coordinator_obs_port,
        "node_manager_port": args.node_manager_port,
        "base_port": getattr(args, "base_port", 10000),
        "tensor_parallel_size": getattr(args, "tensor_parallel_size", None),
        "data_parallel_size": getattr(args, "data_parallel_size", None),
        "gpu_memory_utilization": getattr(args, "gpu_memory_utilization", None),
        "enable_expert_parallel": getattr(args, "enable_expert_parallel", None),
        "max-model-len": getattr(args, "max_model_len", None),
        "max-num-batched-tokens": getattr(args, "max_num_batched_tokens", None),
        "max-num-seqs": getattr(args, "max_num_seqs", None),
        "enforce-eager": getattr(args, "enforce_eager", None),
        "quantization": getattr(args, "quantization", None),
        "tokenizer-mode": getattr(args, "tokenizer_mode", None),
        "tool-call-parser": getattr(args, "tool_call_parser", None),
        "reasoning-parser": getattr(args, "reasoning_parser", None),
        "trust-remote-code": getattr(args, "trust_remote_code", None),
    }
    # Filter out None values so defaults apply
    params = {k: v for k, v in params.items() if v is not None}

    config = build_user_config(params, hw, npu_num)
    os.makedirs(STATE_DIR, exist_ok=True)
    save_json(USER_CONFIG, config)
    logger.info("config saved to %s", USER_CONFIG)
    return config


# ── commands ─────────────────────────────────────────────────────────────

def cmd_check(args):
    """Validate environment before deployment."""
    errors = []

    # docker
    rc, _, _ = run_cmd("docker --version")
    if rc != 0:
        errors.append("docker not found")

    # npu-smi
    rc, _, _ = run_cmd("npu-smi info -m")
    if rc != 0:
        errors.append("npu-smi not found")

    # weight path
    if args.weight_path:
        wp = os.path.abspath(args.weight_path)
        if not os.path.isdir(wp):
            errors.append(f"weight_path not found: {wp}")
        elif os.path.islink(wp):
            errors.append(f"weight_path should not be a symlink: {wp}")

    # model path
    if args.model_path:
        mp = os.path.abspath(args.model_path)
        if not os.path.isdir(mp):
            errors.append(f"model_path not found: {mp}")
        elif args.weight_path and not mp.startswith(os.path.abspath(args.weight_path)):
            errors.append("model_path must be under weight_path")

    # NPU availability
    try:
        hw = detect_hardware_type()
        npus = detect_available_npus(hw)
        logger.info("hardware: %s, available NPUs: %d (%s)", hw, len(npus), npus)
    except RuntimeError as e:
        errors.append(str(e))

    # ports
    ports = [args.controller_port, args.coordinator_infer_port,
             args.coordinator_mgmt_port, args.coordinator_obs_port, args.node_manager_port]
    for p in ports:
        rc, out, _ = run_cmd(f"ss -ltn | grep ':{p} '")
        if out.strip():
            errors.append(f"port {p} already in use")

    if errors:
        raise RuntimeError("; ".join(errors))
    logger.info("environment check passed")


def cmd_start(args):
    """Prepare and start vLLM container."""
    # load config file and merge with CLI args
    file_cfg = _load_config_file(args.config_file)
    _merge_args_from_file(args, file_cfg)
    _validate_start_args(args)

    stop_container()
    # resolve image before saving config so it's persisted
    resources_dir = args.resources_dir or os.path.join(SCRIPT_DIR, "..", "ascend_deployer", "resources")
    image = resolve_vllm_image(args.image, resources_dir)
    save_config_from_args(args, image)
    start_from_config(on_progress=lambda m: logger.info(m))


def cmd_stop(_args):
    """Stop and remove the vLLM container."""
    if stop_container():
        logger.info("container %s stopped and removed", CONTAINER_NAME)
    else:
        logger.info("container %s not running", CONTAINER_NAME)


def cmd_status(_args):
    """Show container and service status."""
    # container status
    rc, out, _ = run_cmd(f"docker inspect -f '{{{{.State.Status}}}}' {CONTAINER_NAME}")
    if rc != 0:
        logger.info("Container: not running")
        return
    logger.info("Container: %s", out)

    # process check
    rc, _, _ = run_cmd(f"docker exec {CONTAINER_NAME} ps aux | grep -v grep | grep mindieservice_daemon > /dev/null")
    if rc == 0:
        logger.info("MindIE Motor: running")
    else:
        grep_pattern = "grep -E 'python|boot.sh'"
        cmd2 = f"docker exec {CONTAINER_NAME} ps aux | grep -v grep | {grep_pattern} > /dev/null"
        rc2, _, _ = run_cmd(cmd2)
        if rc2 == 0:
            logger.info("vLLM Engine: running")
        else:
            logger.info("Engine process: not detected")

    # last few lines of logs
    rc, out, _ = run_cmd(f"docker logs --tail 5 {CONTAINER_NAME}")
    if out:
        logger.info("Last log lines:\n%s", out)

    # config summary
    if os.path.exists(USER_CONFIG):
        cfg = load_json(USER_CONFIG)
        ec = cfg.get("motor_engine_union_config", {}).get("engine_config", {})
        dp = cfg.get("motor_deploy_config", {})
        logger.info("Config:")
        logger.info("  model:           %s", ec.get('model', 'N/A'))
        logger.info("  served_model:    %s", ec.get('served_model_name', 'N/A'))
        logger.info("  npu_num:         %s", dp.get('hybrid_pod_npu_num', 'N/A'))
        logger.info("  tensor_parallel: %s", ec.get('tensor_parallel_size', 'N/A'))
        logger.info("  data_parallel:   %s", ec.get('data_parallel_size', 'N/A'))
        logger.info("  quantization:    %s", ec.get('quantization', 'N/A'))
        logger.info("  expert_parallel: %s", ec.get('enable_expert_parallel', 'N/A'))
        logger.info("  gpu_mem_util:    %s", ec.get('gpu_memory_utilization', 'N/A'))
        logger.info("  max_model_len:   %s", ec.get('max-model-len', 'N/A'))
        logger.info("  max_num_seqs:    %s", ec.get('max-num-seqs', 'N/A'))
        logger.info("  tokenizer_mode:  %s", ec.get('tokenizer-mode', 'N/A'))


def cmd_config(args):
    """Show or modify configuration, then auto-restart."""
    if not os.path.exists(USER_CONFIG):
        raise RuntimeError(f"config not found: {USER_CONFIG}; run 'start' first to generate config")

    cfg = load_json(USER_CONFIG)

    if args.show:
        logger.info(json.dumps(cfg, indent=4, ensure_ascii=False))
        return

    # load config file and merge with CLI args
    file_cfg = _load_config_file(args.config_file)
    _merge_args_from_file(args, file_cfg)

    # modify fields
    changed = False
    ec = cfg["motor_engine_union_config"]["engine_config"]
    coord = cfg["motor_coordinator_config"]["api_config"]
    ctrl = cfg["motor_controller_config"]["api_config"]
    nm = cfg["motor_engine_union_config"]["motor_nodemanger_config"]["api_config"]
    dp = cfg["motor_deploy_config"]

    def _set(d, key, val):
        nonlocal changed
        if val is not None:
            d[key] = val
            changed = True

    # model
    _set(ec, "served_model_name", args.model_name)
    if args.model_path is not None:
        ec["model"] = os.path.abspath(args.model_path)
        changed = True
    if args.weight_path is not None:
        dp["weight_mount_path"] = os.path.abspath(args.weight_path)
        changed = True

    # parallelism & hardware
    if args.npu_num is not None and args.npu_num > 0:
        ec["data_parallel_size"] = args.npu_num
        dp["hybrid_pod_npu_num"] = args.npu_num
        changed = True
    _set(ec, "tensor_parallel_size", args.tensor_parallel_size)
    _set(ec, "data_parallel_size", args.data_parallel_size)
    _set(ec, "quantization", args.quantization)
    if args.enable_expert_parallel is not None:
        ec["enable_expert_parallel"] = bool(args.enable_expert_parallel)
        changed = True
    _set(ec, "gpu_memory_utilization", args.gpu_memory_utilization)

    # inference tuning
    _set(ec, "max-model-len", args.max_model_len)
    _set(ec, "max-num-batched-tokens", args.max_num_batched_tokens)
    _set(ec, "max-num-seqs", args.max_num_seqs)
    if args.enforce_eager is not None:
        ec["enforce-eager"] = bool(args.enforce_eager)
        changed = True

    # model format
    _set(ec, "tokenizer-mode", args.tokenizer_mode)
    _set(ec, "tool-call-parser", args.tool_call_parser)
    _set(ec, "reasoning-parser", args.reasoning_parser)
    if args.trust_remote_code is not None:
        ec["trust-remote-code"] = bool(args.trust_remote_code)
        changed = True

    # ports
    _set(ctrl, "controller_api_port", args.controller_port)
    _set(coord, "coordinator_api_infer_port", args.coordinator_infer_port)
    _set(coord, "coordinator_api_mgmt_port", args.coordinator_mgmt_port)
    _set(coord, "coordinator_obs_port", args.coordinator_obs_port)
    _set(nm, "node_manager_port", args.node_manager_port)

    if not changed:
        logger.info("no changes specified. Use --show to view current config.")
        return

    save_json(USER_CONFIG, cfg)
    logger.info("config updated, restarting container ...")
    stop_container()
    start_from_config(on_progress=lambda m: logger.info(m))


# ── config file loading ──────────────────────────────────────────────────

def _load_config_file(path):
    """Load a JSON config file and return as dict."""
    if not path:
        return {}
    if not os.path.exists(path):
        raise RuntimeError(f"config file not found: {path}")
    try:
        return load_json(path)
    except Exception as e:
        raise RuntimeError(f"failed to parse config file {path}: {e}") from e


def _merge_args_from_file(args, file_cfg):
    """Merge CLI args with config file values. CLI takes precedence.
    Config file uses nested format: {"section": {"key": val}}."""
    # mapping: (section, key) → argparse dest
    sections = {
        "deploy": {
            "image": "image",
            "npu_num": "npu_num",
            "controller_port": "controller_port",
            "coordinator_infer_port": "coordinator_infer_port",
            "coordinator_mgmt_port": "coordinator_mgmt_port",
            "coordinator_obs_port": "coordinator_obs_port",
            "node_manager_port": "node_manager_port",
            "base_port": "base_port",
        },
        "model": {
            "weight_path": "weight_path",
            "model_path": "model_path",
            "model_name": "model_name",
        },
        "parallel": {
            "tensor_parallel_size": "tensor_parallel_size",
            "data_parallel_size": "data_parallel_size",
            "quantization": "quantization",
            "enable_expert_parallel": "enable_expert_parallel",
            "gpu_memory_utilization": "gpu_memory_utilization",
        },
        "inference": {
            "max_model_len": "max_model_len",
            "max_num_batched_tokens": "max_num_batched_tokens",
            "max_num_seqs": "max_num_seqs",
            "enforce_eager": "enforce_eager",
            "safetensors_load_strategy": "safetensors_load_strategy",
            "async_scheduling": "async_scheduling",
            "seed": "seed",
        },
        "format": {
            "tokenizer_mode": "tokenizer_mode",
            "tool_call_parser": "tool_call_parser",
            "reasoning_parser": "reasoning_parser",
            "trust_remote_code": "trust_remote_code",
        },
    }
    for section, key_map in sections.items():
        section_cfg = file_cfg.get(section, {})
        if not isinstance(section_cfg, dict):
            continue
        for json_key, dest in key_map.items():
            file_val = section_cfg.get(json_key)
            if file_val is None:
                continue
            cli_val = getattr(args, dest, None)
            if isinstance(file_val, str):
                if not cli_val:
                    setattr(args, dest, file_val)
            elif isinstance(file_val, (int, float)):
                if cli_val is None or (dest == "npu_num" and cli_val == 0):
                    setattr(args, dest, file_val)
    return args


def _validate_start_args(args):
    """Validate that required start args are present."""
    missing = []
    if not args.weight_path:
        missing.append("--weight-path")
    if not args.model_path:
        missing.append("--model-path")
    if not args.model_name:
        missing.append("--model-name")
    if missing:
        raise RuntimeError(f"missing required args: {', '.join(missing)}; provide via --config-file or CLI args")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="inference_ctl",
        description="Inference Service Control - start/stop/config for MindIE Motor vLLM",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="Prepare and start vLLM container")
    p_start.add_argument("--config-file", default="", help="JSON config file (CLI args override file values)")
    p_start.add_argument("--weight-path", default="", help="Host path to model weights")
    p_start.add_argument("--model-path", default="", help="Model path (under weight-path)")
    p_start.add_argument("--model-name", default="", help="Served model name")
    p_start.add_argument("--image", default="", help="Docker image name (auto-detect if empty)")
    p_start.add_argument("--npu-num", type=int, default=0, help="Number of NPUs (0=auto)")
    # parallelism & hardware
    p_start.add_argument("--tp", type=int, default=None, dest="tensor_parallel_size", help="Tensor parallel size")
    p_start.add_argument("--dp", type=int, default=None, dest="data_parallel_size", help="Data parallel size")
    p_start.add_argument("--quantization", default=None, help="Quantization method")
    p_start.add_argument("--enable-expert-parallel", type=int, default=None, choices=[0, 1],
                          help="Expert parallel for MoE (1=on, 0=off)")
    p_start.add_argument("--gpu-memory-utilization", type=float, default=None, help="GPU memory utilization (0.0-1.0)")
    # inference tuning
    p_start.add_argument("--max-model-len", type=int, default=None, help="Max sequence length")
    p_start.add_argument("--max-num-batched-tokens", type=int, default=None, help="Max batched tokens")
    p_start.add_argument("--max-num-seqs", type=int, default=None, help="Max concurrent sequences")
    p_start.add_argument("--enforce-eager", type=int, default=None, choices=[0, 1],
                          help="Enforce eager mode (1=on, 0=off)")
    # model format
    p_start.add_argument("--tokenizer-mode", default=None, help="Tokenizer mode")
    p_start.add_argument("--tool-call-parser", default=None, help="Tool call parser")
    p_start.add_argument("--reasoning-parser", default=None, help="Reasoning parser")
    p_start.add_argument("--trust-remote-code", type=int, default=None, choices=[0, 1],
                          help="Trust remote code (1=on, 0=off)")
    # ports
    p_start.add_argument("--controller-port", type=int, default=2026)
    p_start.add_argument("--coordinator-infer-port", type=int, default=1025)
    p_start.add_argument("--coordinator-mgmt-port", type=int, default=1030)
    p_start.add_argument("--coordinator-obs-port", type=int, default=1029)
    p_start.add_argument("--node-manager-port", type=int, default=3026)
    p_start.add_argument("--base-port", type=int, default=10000, help="MindIE Motor base port for internal services")

    # stop
    sub.add_parser("stop", help="Stop and remove vLLM container")

    # status
    sub.add_parser("status", help="Show container status")

    # config
    p_config = sub.add_parser("config", help="Show or modify configuration")
    p_config.add_argument("--show", action="store_true", help="Show current config")
    p_config.add_argument("--config-file", default="", help="JSON config file (CLI args override file values)")

    # model
    p_config.add_argument("--model-name", default=None, help="Served model name")
    p_config.add_argument("--model-path", default=None, help="Model weight path")
    p_config.add_argument("--weight-path", default=None, help="Host weight mount path")

    # parallelism & hardware
    p_config.add_argument("--npu-num", type=int, default=None, help="NPU count (data_parallel_size)")
    p_config.add_argument("--tp", type=int, default=None, dest="tensor_parallel_size", help="Tensor parallel size")
    p_config.add_argument("--dp", type=int, default=None, dest="data_parallel_size", help="Data parallel size")
    p_config.add_argument("--quantization", default=None, help="Quantization method (e.g. ascend, awq, gptq)")
    p_config.add_argument("--enable-expert-parallel", type=int, default=None, choices=[0, 1],
                          help="Enable expert parallel for MoE (1=on, 0=off)")
    p_config.add_argument("--gpu-memory-utilization", type=float, default=None, help="GPU memory utilization (0.0-1.0)")

    # inference tuning
    p_config.add_argument("--max-model-len", type=int, default=None, help="Max sequence length")
    p_config.add_argument("--max-num-batched-tokens", type=int, default=None, help="Max batched tokens")
    p_config.add_argument("--max-num-seqs", type=int, default=None, help="Max concurrent sequences")
    p_config.add_argument("--enforce-eager", type=int, default=None, choices=[0, 1],
                          help="Enforce eager mode (1=on, 0=off)")

    # model format
    p_config.add_argument("--tokenizer-mode", default=None, help="Tokenizer mode (e.g. deepseek_v4, auto)")
    p_config.add_argument("--tool-call-parser", default=None, help="Tool call parser (e.g. deepseek_v4)")
    p_config.add_argument("--reasoning-parser", default=None, help="Reasoning parser (e.g. deepseek_v4)")
    p_config.add_argument("--trust-remote-code", type=int, default=None, choices=[0, 1],
                          help="Trust remote code (1=on, 0=off)")

    # ports
    p_config.add_argument("--controller-port", type=int, default=None)
    p_config.add_argument("--coordinator-infer-port", type=int, default=None)
    p_config.add_argument("--coordinator-mgmt-port", type=int, default=None)
    p_config.add_argument("--coordinator-obs-port", type=int, default=None)
    p_config.add_argument("--node-manager-port", type=int, default=None)

    # check
    p_check = sub.add_parser("check", help="Validate environment")
    p_check.add_argument("--weight-path", default="", help="Weight path to validate")
    p_check.add_argument("--model-path", default="", help="Model path to validate")
    p_check.add_argument("--controller-port", type=int, default=2026)
    p_check.add_argument("--coordinator-infer-port", type=int, default=1025)
    p_check.add_argument("--coordinator-mgmt-port", type=int, default=1030)
    p_check.add_argument("--coordinator-obs-port", type=int, default=1029)
    p_check.add_argument("--node-manager-port", type=int, default=3026)

    args = parser.parse_args()
    try:
        {
            "start": cmd_start,
            "stop": cmd_stop,
            "status": cmd_status,
            "config": cmd_config,
            "check": cmd_check,
        }[args.command](args)
    except RuntimeError as e:
        logger.error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
