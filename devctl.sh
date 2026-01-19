#! /bin/bash
set -e
VERSION="2025.12.03"
ME=$0
APP_INFO_FILE=".appinfo"

function usage() {
  echo "usage: $0 <command>"
  echo "commands:"
  echo -e "  init-app <appid>: init app from the app template"
  echo -e "  check: check if the development environment is ready"
  echo -e "  docker: build docker image for deployment on the yuanqi platform"
  echo -e "  sidecar: start/stop the sidecar"
  echo
  echo "version: $VERSION"
  exit 1
}

function precheck() {
  issue_found=false
  if ! which zbxctl >/dev/null 2>&1; then
    echo "error: zbxctl not installed, please install it first"
    issue_found=true
  fi

  if [[ ! -f $HOME/.zebrax/config.yaml ]]; then
    echo "error: zbxctl is not logged into the yuanqi platform, please login first"
    issue_found=true
  fi

  if ! docker ps >/dev/null 2>&1; then
    echo "warning: docker does not work properly, build docker image and dev container will not work properly without docker"
    issue_found=true
  fi

  if [[ $issue_found == true ]]; then
    echo
    echo "please fix the above environment issues and try again"
    exit 1
  else
    echo "no environment issue(s) found"
  fi
}

function init_app() {
  app_id=$1
  if [[ -z $app_id ]]; then
    echo "err: missing required argument appid"
    exit 1
  fi

  # create .appinfo file
  echo "APP_ID=$app_id" >$APP_INFO_FILE
  sed -i.bak "s/{{APP_ID}}/${app_id}/g" Bdefile && rm Bdefile.bak

  echo "python app $app_id initialized successfully"
}

function check_zbxctl() {
    echo
}

function init_env() {
  if [[ -f $APP_INFO_FILE ]]; then
    source ${APP_INFO_FILE}
    if [[ -z $APP_ID ]]; then
      echo "APP_ID not defined in $APP_INFO_FILE file"
      exit 1
    fi
  else
    echo "file $APP_INFO_FILE not found. please init app first by running '$ME init-app <your_app_id>'"
    exit 1
  fi

  if [[ -f .devctl.env ]]; then
    source .devctl.env
  fi

  ZBXCTL_CMD="${ZBXCTL_CMD:-zbxctl}"
  ZBXCTL_CFG="${ZBXCTL_CFG:-${HOME}/.zebrax/config.yaml}"
  
  # 确保 PATH 包含 zbxctl 可能存在的目录
  if ! command -v $ZBXCTL_CMD >/dev/null 2>&1; then
    if [[ -d "$HOME/.local/bin" ]]; then
      export PATH="$HOME/.local/bin:$PATH"
    fi
  fi

}

function build_docker() {
  if [[ -n $RC_ROOT ]]; then
    echo "err: cannot build docker image in bde development container."
    exit 1
  fi

  do_push=false
  do_deploy=false
  dev_mode=false
  while [[ $# -gt 0 ]]; do
    case $1 in
      -h | --help)
        echo "usage: $0 docker, build docker image, with the following additional options:"
        echo "  -p  | --push: push the docker image to the registry"
        echo "  -d  | --deploy: deploy the docker image to the yuanqi platform"
        echo "  -dd | --dev-deploy: deploy the docker image in development mode, which automatically become the active version"
        echo "  -e  | --envs: deployment environments，only takes effect when either -d or -dd is set. if not set, default value is default environment"
        exit 1
        ;;
      --push | -p)
        do_push=true
        ;;
      --deploy | -d)
        do_deploy=true
        ;;
      --dev-deploy | -dd | --dd)
        do_deploy=true
        dev_mode=true
        ;;
      --envs | -e)
        shift
        envs=$1
        if [[ -z $envs ]]; then
          echo "Error: The --envs parameter requires a value."
          exit 1
        fi
        ;;
      *)
        echo "unknown option: $1"
        exit 1
        ;;
    esac
    shift
  done

  repo="ebanma/llm-agent:$APP_ID"
  ver=$(date +%Y%m%d-%H%M%S)
  tag=${repo}_${ver}
  check_uncommitted_changes

  docker build --platform linux/amd64 --network host --build-arg ARG_APP_ID=$APP_ID -t ${tag} -t ${repo}_latest -f docker/Dockerfile .

  local latest_version="latest"
  if [[ $do_push == true || $do_deploy == true ]]; then
    if [[ -z $REGISTRY ]]; then
      echo "err: registry not set, unable to push, please set REGISTRY env variable"
      exit 1
    fi
    check_zbxctl
    remote_tag=${REGISTRY}/${tag}
    remote_tag_vpc=${remote_tag}
    if [[ -n $REGISTRY_VPC ]]; then
      remote_tag_vpc=${REGISTRY_VPC}/${tag}
    fi
    docker tag ${tag} ${remote_tag}
    docker push ${remote_tag}
    echo "docker image is pushed: ${remote_tag}"

    # create version in yuanqi platform
    local git_branch=$(git rev-parse --abbrev-ref HEAD)
    local commit_id=$(git show -s --format=%h)
    local commit_msg=$(git log -1 --pretty=format:%s)

    # create version
    $ZBXCTL_CMD --config $ZBXCTL_CFG llm app version create --app-id $APP_ID --version $ver --docker ${remote_tag_vpc} --commit-id $commit_id --branch ${git_branch} --description "${commit_msg}"
  fi

  if [[ $do_deploy == true ]]; then
    deploy_args="--app-id $APP_ID --wait"
    deploy_version=$ver
    if [[ $dev_mode == true ]]; then
      deploy_args="${deploy_args} --online"
    fi
    deploy_args="${deploy_args} --version ${deploy_version}"

    if [[ -n $envs ]]; then
      deploy_args="${deploy_args} --envs ${envs}"
    fi

    deploy_cmd="$ZBXCTL_CMD --config $ZBXCTL_CFG llm app version deploy $deploy_args"

    echo
    echo "start deploying app $APP_ID"
    eval $deploy_cmd
  fi
}

function check_uncommitted_changes() {
    local status=$(git status --porcelain)
    if [ -n "$status" ]; then
        git status
        echo "You have uncommitted files, please ensure this is expected, deployment will continue in 5 seconds"
        echo
        sleep 5
    fi
}

function check_sidecar_status {
  CHECK_URL="http://localhost:13984/status.zebra"
  HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}\n" $CHECK_URL)
  if [ "$HTTP_STATUS" -eq "200" ]; then
    return 0
  else
    return 1
  fi
}

function sidecar_usage() {
  echo "Usage: $ME sidecar [start|stop|restart|status]"
  exit 1
}

function sidecar() {
  if [[ $# == 0 ]]; then
    sidecar_usage
  fi

  case $1 in
  start)
    shift 1
    start_sidecar_v2
    ;;
  stop)
    shift 1
    stop_sidecar
    ;;
  restart)
    shift 1
    stop_sidecar
    start_sidecar_v2
    ;;
  status)
    shift 1
    check_sidecar_status
    if [ $? -eq 0 ]; then
      echo "sidecar is running"
    else
      echo "sidecar is not running"
    fi
    ;;
  *)
    sidecar_usage
    ;;
  esac
}

function stop_sidecar() {
  # Find the PID(s) of the process 'zbxctl llm sidecar'
  set +e
  PIDS=$(pgrep -f 'zbxctl llm sidecar')

  if [[ -z $PIDS ]]; then
    echo "llm sidecar server is not running"
  else
    # Kill the process(es)
    echo "killing sidecar pids: $PIDS"
    kill -9 $PIDS
  fi
}

function start_sidecar_v2() {
  CHECK_URL="http://localhost:13984/status.zebra"
  LOG_FILE="logs/sidecar.log"
  mkdir -p logs
  # 确保日志文件可写（如果文件存在且不可写，则删除）
  if [[ -f "$LOG_FILE" && ! -w "$LOG_FILE" ]]; then
    echo "warning: $LOG_FILE exists but is not writable, removing it..."
    rm -f "$LOG_FILE" 2>/dev/null || {
      echo "error: cannot remove $LOG_FILE, please check permissions"
      return 1
    }
  fi
  # 确保使用完整路径或确保 PATH 包含 zbxctl 所在目录
  if ! command -v $ZBXCTL_CMD >/dev/null 2>&1; then
    # 如果 zbxctl 不在 PATH 中，尝试使用完整路径
    if [[ -f "$HOME/.local/bin/zbxctl" ]]; then
      ZBXCTL_CMD="$HOME/.local/bin/zbxctl"
    elif [[ -f "/usr/local/bin/zbxctl" ]]; then
      ZBXCTL_CMD="/usr/local/bin/zbxctl"
    else
      echo "error: zbxctl not found in PATH or common locations"
      echo "please ensure zbxctl is installed and in your PATH"
      return 1
    fi
  fi
  START_COMMAND="LLM_ENV=${LLM_ENV:-dev} LLM_AGENT_ENV=${LLM_AGENT_ENV:-default} LLM_APP_ID=$APP_ID LLM_USE_CONFIG_API=1 $ZBXCTL_CMD llm sidecar --debug --config $ZBXCTL_CFG"

  # 检查 URL 是否可访问
  if check_sidecar_status; then
    echo "sidecar is already running"
    return 0
  else
    echo "starting the sidecar service..."
    echo "cmd = $START_COMMAND"

    # 执行启动命令
    eval $START_COMMAND >"$LOG_FILE" 2>&1 &
    START_PID=$!
  fi

  # 等待 URL 可访问
  until check_sidecar_status; do
    echo "waiting for sidecar to become accessible..."
    # 动态展示日志
    tail -f $LOG_FILE | while read line; do
      echo $line
      # 再次检查 URL
      if check_sidecar_status; then
        echo "sidecar is now accessible, pid = $START_PID. see logs in $LOG_FILE"
        pkill -P $$ tail # 终止 tail 进程
        break
      fi
      sleep 0.1
    done
  done
}

# main
if [ $# -lt 1 ]; then
  usage
fi

# specially handle init_app for the first time
if [[ $1 == "init-app" ]]; then
  shift 1
  init_app $@
  exit 0
fi

init_env
case $1 in
check)
  shift 1
  precheck
  ;;
docker)
  shift 1
  build_docker $@
  ;;
sidecar)
  shift 1
  sidecar $@
  ;;
*)
  echo "unknown command: $1"
  usage
  ;;
esac
