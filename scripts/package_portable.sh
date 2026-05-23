#!/usr/bin/env bash
set -euo pipefail

workflow="build-artifacts.yml"

gh workflow run "$workflow"
sleep 5
run_id="$(gh run list --workflow "$workflow" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$run_id" --exit-status
mkdir -p portable-dist
gh run download "$run_id" --dir portable-dist
printf '\nArtifacts downloaded to %s/portable-dist\n' "$(pwd)"
