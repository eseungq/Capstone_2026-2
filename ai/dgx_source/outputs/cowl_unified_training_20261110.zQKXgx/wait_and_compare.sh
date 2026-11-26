set -euo pipefail
stage=$1 paths=$2 runtime=$3
echo "WAITING_FOR_TRAINING_AND_DOOR_RECOVERY"
for ((poll=0; poll<1050; poll++)); do
    if test -s "$stage/result.txt" && grep -q '^door_restored=' "$stage/result.txt"; then
        grep -Fxq 'training_exit=0' "$stage/result.txt"
        ! grep -Fxq 'door_restored=unconfirmed' "$stage/result.txt"
        curl -fsS --max-time 5 http://127.0.0.1:8771/internal/v1/models
        exec env CUDA_VISIBLE_DEVICES= PYTHONPATH="$paths" PYTHONDONTWRITEBYTECODE=1 "$runtime" -u "$stage/evaluate_cowl_unified.py" "$stage"
    fi
    sleep 30
done
echo 'Timed out waiting for the training supervisor'
exit 1
