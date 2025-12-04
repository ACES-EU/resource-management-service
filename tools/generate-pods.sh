#!/bin/bash

COUNT=15
SLEEP_TIME_SECONDS=5
SCHEDULER="resource-management-service"
IMAGE="nginx"

declare -A CPU_REQS=(
  ["small"]="50m"
  ["medium"]="200m"
  ["large"]="500m"
  ["xl"]="1000m"
)

declare -A MEM_REQS=(
  ["small"]="64Mi"
  ["medium"]="256Mi"
  ["large"]="512Mi"
  ["xl"]="1024Mi"
)

random_range() {
    min=$1
    max=$2
    echo $((RANDOM % (max - min + 1) + min))
}

# Bucket distribution (change weights by repeating entries)
BUCKETS=("small" "small" "medium" "medium" "large" "large" "xl")

# Chance (0–10) that ANY bucket gets limits
LIMIT_PROB=3   # 30%

TEMPLATE_FILE="tools/pod-template.yaml"

for i in $(seq 1 $COUNT); do
    # pick bucket
    idx=$(shuf -i 0-$((${#BUCKETS[@]} - 1)) -n 1)
    BUCKET="${BUCKETS[$idx]}"

    CPU_REQ="${CPU_REQS[$BUCKET]}"
    MEM_REQ="${MEM_REQS[$BUCKET]}"

    # limits or not?
    roll=$(random_range 1 10)
    if (( roll <= LIMIT_PROB )); then
	CPU_LIMIT="`random_range ${CPU_REQ%m} 2000`m"
	MEM_LIMIT="`random_range ${MEM_REQ%Mi} 4096`Mi"
        LIMITS_BLOCK=`echo -ne "        limits:\n          cpu: \"${CPU_LIMIT}\"\n          memory: \"${MEM_LIMIT}\"\n"`
    else
        LIMITS_BLOCK=""
    fi

    NAME="test-pod-$i"

    # Export all environment variables for envsubst
    export NAME BUCKET SCHEDULER IMAGE CPU_REQ MEM_REQ LIMITS_BLOCK

    envsubst < "$TEMPLATE_FILE" | kubectl apply -n lake -f -

    echo "Created $NAME in bucket $BUCKET (req=${CPU_REQ}/${MEM_REQ}, limits=${CPU_LIMIT:-none}/${MEM_LIMIT:-none})"

    sleep $SLEEP_TIME_SECONDS
done

