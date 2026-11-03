// GitLab branch automation - Azure resources
//
// Creates:
//   * User Assigned Managed Identity (UAMI) used by the Function App at runtime
//     and by GitHub Actions through OIDC federation (no client secrets anywhere)
//   * Key Vault (RBAC mode) holding the GitLab token and webhook secret
//   * Linux Function App (Python) on a Consumption plan + storage + App Insights
//
// Deploy with infra/deploy.sh (see docs/DEPLOYMENT.md).

targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short prefix used in resource names (lowercase letters and digits, max 10).')
@maxLength(10)
param namePrefix string = 'glbranch'

@description('GitHub repository allowed to log in as the UAMI, as owner/repo.')
param githubRepo string

@description('Branch whose workflows may log in as the UAMI (scheduled workflows run on the default branch).')
param githubBranch string = 'main'

@description('Object id of the person/group running setup locally; gets Key Vault Secrets Officer. Leave empty to skip.')
param adminPrincipalId string = ''

@description('Python version for the Function App.')
@allowed(['3.11', '3.12'])
param pythonVersion string = '3.11'

var suffix = uniqueString(resourceGroup().id)
var tags = {
  workload: 'gitlab-branch-automation'
}

// Built-in role definition ids
var roleKeyVaultSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
var roleWebsiteContributor = 'de139f84-1756-47ae-9be6-808fbbe84772'

// ---------------------------------------------------------------- identity
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${namePrefix}-${suffix}'
  location: location
  tags: tags
}

resource githubFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: uami
  name: 'github-actions'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepo}:ref:refs/heads/${githubBranch}'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

// ---------------------------------------------------------------- key vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv-${namePrefix}-${suffix}', 24)
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    publicNetworkAccess: 'Enabled'
  }
}

// The UAMI reads secrets in the function and writes them during rotation.
resource uamiSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, uami.id, roleKeyVaultSecretsOfficer)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsOfficer)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource adminSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adminPrincipalId)) {
  name: guid(keyVault.id, adminPrincipalId, roleKeyVaultSecretsOfficer)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsOfficer)
    principalId: adminPrincipalId
  }
}

// ---------------------------------------------------------------- monitoring
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}-${suffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ---------------------------------------------------------------- function app
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${namePrefix}${suffix}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-${namePrefix}-${suffix}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true // Linux
  }
}

var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}'

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: 'func-${namePrefix}-${suffix}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: uami.id
    siteConfig: {
      linuxFxVersion: 'Python|${pythonVersion}'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: storageConnection }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'KEYVAULT_URL', value: keyVault.properties.vaultUri }
        { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
      ]
    }
  }
}

// Lets GitHub Actions (logged in as the UAMI) deploy code to this Function App.
resource uamiWebsiteContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionApp.id, uami.id, roleWebsiteContributor)
  scope: functionApp
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleWebsiteContributor)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------- outputs
output functionAppName string = functionApp.name
output webhookUrl string = 'https://${functionApp.properties.defaultHostName}/api/gitlab-webhook'
output keyVaultName string = keyVault.name
output keyVaultUrl string = keyVault.properties.vaultUri
output uamiClientId string = uami.properties.clientId
output tenantId string = subscription().tenantId
output subscriptionId string = subscription().subscriptionId
