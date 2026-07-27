#!/usr/bin/env bash
set -euo >/dev/null 2>&1

gateway_get_config_dir() {
    local instance_name="${DEPLOY_VARS["JIUWENSWARM_INSTANCE_NAME"]}"
    if [ -n "${instance_name}" ]; then
        echo "/root/.jiuwenswarm-instances/${instance_name}/config"
    else
        echo "/root/.jiuwenswarm/config"
    fi
}

gateway_resolve_host() {
    local master_host="${DEPLOY_VARS["MASTER_NODE_IP"]:-}"
    if [ -z "${master_host}" ]; then
        if [ -n "${DEPLOY_VARS["CLUSTER_HOSTS"]:-}" ]; then
            IFS=',' read -ra _gw_host_list <<< "${DEPLOY_VARS["CLUSTER_HOSTS"]}"
            master_host="${_gw_host_list[0]}"
        else
            master_host=$(get_local_ip)
            info "MASTER_NODE_IP not set, defaulting to local: ${master_host}" >&2
        fi
    fi
    echo "${master_host}"
}

gateway_compute_extension_dirs() {
    if [ -n "${DEPLOY_VARS["EXTENSION_DIRS"]:-}" ]; then
        info "EXTENSION_DIRS already set: ${DEPLOY_VARS["EXTENSION_DIRS"]}"
        return 0
    fi

    local master_host
    master_host=$(gateway_resolve_host)
    local python_version="${DEPLOY_VARS["YR_PYTHON_VERSION"]}"

    local jiuwenswarm_location
    jiuwenswarm_location=$(exec_on_host "${master_host}" "python${python_version} -m pip show jiuwenswarm 2>/dev/null | grep -i '^Location:' | awk '{print \$2}'" | tr -d '\r') || true

    if [ -n "${jiuwenswarm_location}" ]; then
        DEPLOY_VARS["EXTENSION_DIRS"]="${jiuwenswarm_location}/jiuwenswarm/extensions"
        info "EXTENSION_DIRS inferred from jiuwenswarm install on ${master_host}: ${DEPLOY_VARS["EXTENSION_DIRS"]}"
    else
        warning "Could not infer EXTENSION_DIRS: jiuwenswarm not found on ${master_host}. You may set EXTENSION_DIRS in .env.custom manually."
    fi
}

gateway_gen_config() {
    gateway_compute_extension_dirs

    info "Generating gateway config.yaml from template..."
    render_config_template "${GATEWAY_CONFIG_TEMPLATE_FILE}" "${GATEWAY_CONFIG_FILE}" "DEPLOY_VARS"

    info "Generating gateway .env from DEPLOY_VARS..."
    write_env_to_file "${GATEWAY_ENV_FILE}" "DEPLOY_VARS"

    local config_dir
    config_dir=$(gateway_get_config_dir)
    info "Gateway config will be deployed to: ${config_dir}/"
    success "Gateway config files generated"
}

gateway_deploy_process() {
    local master_host
    master_host=$(gateway_resolve_host)
    local instance_name="${DEPLOY_VARS["JIUWENSWARM_INSTANCE_NAME"]}"

    info "Deploying gateway in process mode on ${master_host}..."

    gateway_gen_config

    local config_dir
    config_dir=$(gateway_get_config_dir)

    local init_cmd="jiuwenswarm-init -f </dev/null"
    # === 2026-07-27: 注入 GATEWAY_HOST/GATEWAY_PORT/WEB_PORT 让 gateway 对外监听 ===
    # app_gateway.py 读 os.getenv("GATEWAY_HOST","127.0.0.1") / GATEWAY_PORT / WEB_PORT
    local gw_host="${DEPLOY_VARS["GATEWAY_HOST"]:-0.0.0.0}"
    local gw_port="${DEPLOY_VARS["GATEWAY_PORT"]:-19001}"
    local web_port="${DEPLOY_VARS["WEB_PORT"]:-19000}"
    local start_cmd="GATEWAY_HOST=${gw_host} GATEWAY_PORT=${gw_port} WEB_PORT=${web_port} nohup jiuwenswarm-gateway </dev/null > /tmp/jiuwenswarm-gateway.log 2>&1 &"

    if [ -n "${instance_name}" ]; then
        init_cmd="JIUWENSWARM_DATA_DIR=/root/.jiuwenswarm-instances/${instance_name} jiuwenswarm-init -f </dev/null"
        start_cmd="JIUWENSWARM_DATA_DIR=/root/.jiuwenswarm-instances/${instance_name} GATEWAY_HOST=${gw_host} GATEWAY_PORT=${gw_port} WEB_PORT=${web_port} nohup jiuwenswarm-gateway </dev/null > /tmp/jiuwenswarm-gateway.log 2>&1 &"
    fi

    info "Running jiuwenswarm-init on ${master_host}..."
    if exec_on_host "${master_host}" "${init_cmd}"; then
        success "jiuwenswarm-init completed on ${master_host}"
    else
        error "Failed to run jiuwenswarm-init on ${master_host}"
    fi

    info "Copying gateway config.yaml and .env to ${master_host}:${config_dir}/..."
    exec_on_host "${master_host}" "mkdir -p ${config_dir}"
    copy_to_host "${master_host}" "${GATEWAY_CONFIG_FILE}" "${config_dir}/config.yaml"
    copy_to_host "${master_host}" "${GATEWAY_ENV_FILE}" "${config_dir}/.env"

    info "Starting jiuwenswarm-gateway on ${master_host}..."
    exec_on_host "${master_host}" "bash -c '${start_cmd}'"

    local retry=0
    local max_retry=10
    while [ ${retry} -lt ${max_retry} ]; do
        sleep 2
        if exec_on_host "${master_host}" "pgrep -f '[j]iuwenswarm-gateway' >/dev/null 2>&1"; then
            success "Gateway process is running on ${master_host}"
            gateway_deploy_web "${master_host}"
            return 0
        fi
        retry=$((retry + 1))
        info "Waiting for gateway to start... (${retry}/${max_retry})"
    done

    error "Gateway process failed to start on ${master_host}, check /tmp/jiuwenswarm-gateway.log"
}

# === 2026-07-27: 拉起 web 前端静态服务（一键 web 支持）===
# app_web.py 读 os.getenv("FRONTEND_HOST","localhost") / FRONTEND_PORT / WEB_PORT / GATEWAY_URL
gateway_deploy_web() {
    local master_host="$1"
    local web_enabled="${DEPLOY_VARS["WEB_ENABLED"]:-yes}"

    if [ "${web_enabled}" != "yes" ]; then
        info "WEB_ENABLED != yes, skip starting web frontend"
        return 0
    fi

    local fe_host="${DEPLOY_VARS["FRONTEND_HOST"]:-0.0.0.0}"
    local fe_port="${DEPLOY_VARS["WEB_STATIC_PORT"]:-5173}"
    local web_port="${DEPLOY_VARS["WEB_PORT"]:-19000}"

    info "Starting jiuwenswarm-web (frontend static) on ${master_host}: ${fe_host}:${fe_port} ..."
    # 先清掉残留 web 进程（避免端口占用）。
    # 用 [c]hannels 方括号 trick：让 pgrep 的匹配模式本身不含字面串 'channels.web.app_web'，
    # 否则 pgrep 会匹配到 "bash -c '...channels.web.app_web...'" 这个父 shell 命令行而自杀。
    exec_on_host "${master_host}" "pgrep -f '[c]hannels.web.app_web' | xargs -r kill -9 >/dev/null 2>&1 || true"
    # 用 setsid + nohup 让 web 完全脱离 exec_on_host 的 bash -c 子 shell，
    # 否则子 shell 返回时进程组会收 SIGHUP 导致 web 被杀（容器内实测）。
    # exec_on_host 本地分支即 bash -c "$*"，故直接把完整命令串传入即可。
    local web_cmd="FRONTEND_HOST=${fe_host} FRONTEND_PORT=${fe_port} WEB_PORT=${web_port} GATEWAY_URL=http://127.0.0.1:${web_port} setsid nohup jiuwenswarm-web </dev/null > /tmp/jiuwenswarm-web.log 2>&1 & disown"
    exec_on_host "${master_host}" "${web_cmd}"

    local wretry=0
    local wmax=10
    while [ ${wretry} -lt ${wmax} ]; do
        sleep 2
        if exec_on_host "${master_host}" "pgrep -f '[j]iuwenswarm-web' >/dev/null 2>&1"; then
            success "Web frontend is running on ${master_host}: http://${fe_host}:${fe_port} (proxy -> 127.0.0.1:${web_port})"
            echo "  Web UI:  http://<host-ip>:${fe_port}"
            return 0
        fi
        wretry=$((wretry + 1))
        info "Waiting for web to start... (${wretry}/${wmax})"
    done
    warning "Web frontend failed to start on ${master_host}, check /tmp/jiuwenswarm-web.log (gateway still OK)"
}

gateway_undeploy_web() {
    local master_host="$1"
    info "Stopping jiuwenswarm-web on ${master_host}..."
    exec_on_host "${master_host}" "pkill -f '[j]iuwenswarm-web' >/dev/null 2>&1 || true"
    exec_on_host "${master_host}" "pkill -f '[j]iuwenswarm.channels.web.app_web' >/dev/null 2>&1 || true"
    success "Web frontend stopped on ${master_host}"
}

gateway_undeploy_process() {
    local master_host
    master_host=$(gateway_resolve_host)
    local instance_name="${DEPLOY_VARS["JIUWENSWARM_INSTANCE_NAME"]}"

    info "Stopping gateway on ${master_host}..."

    # === 2026-07-27: 同时停 web 前端 ===
    gateway_undeploy_web "${master_host}"

    if [ -n "${instance_name}" ]; then
        exec_on_host "${master_host}" "pkill -f 'JIUWENSWARM_DATA_DIR=/root/.jiuwenswarm-instances/${instance_name}.*[j]iuwenswarm-gateway' || true"
    else
        exec_on_host "${master_host}" "pkill -f '[j]iuwenswarm-gateway' || true"
    fi

    success "Gateway stopped on ${master_host}"
}

deploy_gateway() {
    gateway_deploy_process
}

uninstall_gateway() {
    gateway_undeploy_process
}
