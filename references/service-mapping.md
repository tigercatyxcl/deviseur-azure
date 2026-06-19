# Azure Service Name Mapping Reference

Maps common user terminology to exact Azure Retail Prices API `serviceName` values.

## VM SKU Name Patterns

Users may provide SKU names in various formats. Normalize to `Standard_` prefix:
- `D48as_v6` → `Standard_D48as_v6`
- `Standard_D48as_v6` → `Standard_D48as_v6` (already correct)
- `d48as_v6` → `Standard_D48as_v6` (lowercase)

## Service Name Mappings

### Compute Services

| User Says | API serviceName |
|-----------|----------------|
| vm, virtual machine, compute | `Virtual Machines` |
| vmss, scale set | `Virtual Machine Scale Sets` |
| app service, web app | `Azure App Service` |
| functions, serverless | `Functions` |
| container instance, aci | `Container Instances` |
| aks, kubernetes, k8s | `Azure Kubernetes Service` |
| batch | `Batch` |

### Storage Services

| User Says | API serviceName |
|-----------|----------------|
| storage, blob, file storage | `Storage` |
| managed disk, disk | `Storage` |
| data lake, adls | `Azure Data Lake Storage` |

### Database Services

| User Says | API serviceName |
|-----------|----------------|
| sql, sql database, azure sql | `SQL Database` |
| sql managed instance | `SQL Managed Instance` |
| cosmos, cosmosdb | `Azure Cosmos DB` |
| mysql | `Azure Database for MySQL` |
| postgresql, postgres | `Azure Database for PostgreSQL` |
| redis, redis cache | `Redis Cache` |
| synapse | `Azure Synapse Analytics` |

### Networking Services

| User Says | API serviceName |
|-----------|----------------|
| bandwidth, data transfer, egress | `Bandwidth` |
| load balancer | `Load Balancer` |
| application gateway, app gateway | `Application Gateway` |
| vpn, vpn gateway | `VPN Gateway` |
| expressroute | `ExpressRoute` |
| cdn | `Content Delivery Network` |
| firewall | `Azure Firewall` |
| bastion | `Azure Bastion` |
| front door | `Azure Front Door Service` |

### AI & Machine Learning

| User Says | API serviceName |
|-----------|----------------|
| cognitive services, ai | `Cognitive Services` |
| machine learning, ml | `Azure Machine Learning` |
| openai, gpt, azure openai | `Azure OpenAI Service` |

### Integration & Messaging

| User Says | API serviceName |
|-----------|----------------|
| service bus | `Service Bus` |
| event hubs | `Event Hubs` |
| event grid | `Event Grid` |
| logic apps | `Logic Apps` |
| api management, apim | `API Management` |

### Monitoring & Management

| User Says | API serviceName |
|-----------|----------------|
| monitor, log analytics | `Azure Monitor` |
| backup | `Backup` |
| site recovery | `Site Recovery` |
| arc | `Azure Arc` |
| key vault | `Key Vault` |

## Region Name Mapping

Common aliases:
- us east, east us → `eastus`
- us west, west us → `westus`
- west europe → `westeurope`
- north europe → `northeurope`
- uk south → `uksouth`
- southeast asia → `southeastasia`
- australia east → `australiaeast`
- japan east → `japaneast`
