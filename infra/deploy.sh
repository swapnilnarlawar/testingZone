#!/usr/bin/env bash
# Deploy (or update) the Azure resources and print the GitHub settings to configure.
#
# Usage:
#   ./infra/deploy.sh -g <resource-group> -r <github-owner/repo> [-l <location>] [-p <name-prefix>] [-b <branch>]
#
# Requires: Azure CLI (az) logged in with rights to create resources and role
# assignments in the resource group (Owner, or Contributor + User Access Administrator).
set -euo pipefail

LOCATION="eastus"
PREFIX="glbranch"
BRANCH="main"
RG=""
REPO=""

usage() { sed -n '2,9p' "$0"; exit 1; }
while getopts "g:r:l:p:b:h" opt; do
  case $opt in
    g) RG="$OPTARG" ;;
    r) REPO="$OPTARG" ;;
    l) LOCATION="$OPTARG" ;;
    p) PREFIX="$OPTARG" ;;
    b) BRANCH="$OPTARG" ;;
    *) usage ;;
  esac
done
[[ -z "$RG" || -z "$REPO" ]] && usage

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking Azure login"
az account show --query "{subscription:name, id:id}" -o table

echo "==> Ensuring resource group '$RG' in $LOCATION"
az group create --name "$RG" --location "$LOCATION" --tags workload=gitlab-branch-automation -o none

# The signed-in user gets Key Vault Secrets Officer so they can run 'store-token' and 'setup'.
ADMIN_ID="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
if [[ -z "$ADMIN_ID" ]]; then
  echo "    (could not resolve signed-in user; grant yourself 'Key Vault Secrets Officer' manually)"
fi

echo "==> Deploying infra/main.bicep (takes a few minutes)"
OUTPUTS="$(az deployment group create \
  --resource-group "$RG" \
  --name gitlab-branch-automation \
  --template-file "$SCRIPT_DIR/main.bicep" \
  --parameters namePrefix="$PREFIX" githubRepo="$REPO" githubBranch="$BRANCH" adminPrincipalId="$ADMIN_ID" \
  --query properties.outputs -o json)"

out() { echo "$OUTPUTS" | python3 -c "import json,sys; print(json.load(sys.stdin)['$1']['value'])"; }

FUNC_APP="$(out functionAppName)"
WEBHOOK_URL="$(out webhookUrl)"
KV_URL="$(out keyVaultUrl)"
CLIENT_ID="$(out uamiClientId)"
TENANT_ID="$(out tenantId)"
SUB_ID="$(out subscriptionId)"

cat <<SUMMARY

==> Deployment complete

  Function App : $FUNC_APP
  Webhook URL  : $WEBHOOK_URL
  Key Vault    : $KV_URL
  UAMI client  : $CLIENT_ID

Next steps (also in docs/DEPLOYMENT.md):

1. Configure GitHub (needs the GitHub CLI, run from your clone of $REPO):

   gh secret set AZURE_CLIENT_ID       --body "$CLIENT_ID"
   gh secret set AZURE_TENANT_ID       --body "$TENANT_ID"
   gh secret set AZURE_SUBSCRIPTION_ID --body "$SUB_ID"
   gh variable set AZURE_RESOURCE_GROUP --body "$RG"
   gh variable set FUNCTION_APP_NAME    --body "$FUNC_APP"
   gh variable set KEYVAULT_URL         --body "$KV_URL"
   gh variable set WEBHOOK_URL          --body "$WEBHOOK_URL"

2. For running the ops scripts locally, put these in .env:

   KEYVAULT_URL=$KV_URL
   WEBHOOK_URL=$WEBHOOK_URL

3. Store the GitLab token:   python scripts/webhooks.py store-token
4. Deploy the function:      push to $BRANCH, or run the "Deploy Function" workflow
5. Create the webhooks:      python scripts/webhooks.py setup
6. Verify end to end:        python scripts/webhooks.py verify
SUMMARY
